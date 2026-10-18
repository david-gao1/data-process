"""Offline checks for this config's restricted rules; not a replacement for GitLab CI Lint."""
import json
from pathlib import Path
import re

import yaml


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader,node,deep=False):
    mapping={}
    for key_node,value_node in node.value:
        key=loader.construct_object(key_node,deep=deep)
        if key in mapping: raise ValueError('duplicate YAML key')
        mapping[key]=loader.construct_object(value_node,deep=deep)
    return mapping


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,unique_mapping)


def matches(expression,env):
    for term in expression.split('&&'):
        match=re.fullmatch(r'\s*\$([A-Z_]+)(?:\s*==\s*(?:"([^"]*)"|\$([A-Z_]+)))?\s*',term)
        if not match: raise ValueError('offline evaluator only supports this config\'s documented ==/&& subset')
        left=env.get(match[1],'')
        valid=(left==env.get(match[3],'')) if match[3] else ((left==match[2]) if match[2] is not None else bool(left))
        if not valid:return False
    return True


def selected(rules,env):
    for rule in rules:
        if 'if' not in rule or matches(rule['if'],env):return rule.get('when','on_success')
    return 'never'


def validate(path):
    config=yaml.load(Path(path).read_text(),Loader=UniqueLoader)
    jobs=('core_test','build_wheel','installed_wheel','public_retail_manual')
    assert 'image' not in config['default']
    assert config['default']['tags']==['data-process-local-shell']
    assert config['variables']['GIT_STRATEGY']=='clone' and config['variables']['GIT_DEPTH']=='0'
    assert config['default']['retry']==0 and 'services' not in config['default']
    allowed={'.ci-reports/junit.xml','.ci-reports/source-smoke.json','.ci-reports/installed-smoke.json',
             '.ci-reports/public-status.json','dist/*.whl','dist/manifest.json','dist/runtime-requirements.txt'}
    for job in jobs:
        artifacts=config[job]['artifacts']
        if artifacts['access']!='developer' or not artifacts['expire_in']:raise ValueError('artifact access/retention missing')
        if not set(artifacts['paths'])<=allowed:raise ValueError('artifact is outside the curated software/status allowlist')
    scenarios=[('push','main','true',True),('web','main','true',True),
               ('push','main','false',False),('web','main','false',False),
               ('push','feature','true',False),('web','feature','true',False),
               ('merge_request_event','main','true',False),('push','','true',False),
               ('schedule','main','true',False),('api','main','true',False)]
    for source,branch,protected,expected in scenarios:
        env={'CI_PIPELINE_SOURCE':source,'CI_COMMIT_BRANCH':branch,'CI_COMMIT_REF_PROTECTED':protected}
        assert (selected(config['workflow']['rules'],env)!='never')==expected,(source,branch,protected)
    public_rules=config['public_retail_manual']['rules']
    for source,branch,enabled,wanted in [('push','main','1','never'),('merge_request_event','feature','1','never'),
                                          ('web','main','0','never'),('web','main','1','manual'),('web','feature','1','never')]:
        env={'CI_PIPELINE_SOURCE':source,'CI_COMMIT_BRANCH':branch,'CI_DEFAULT_BRANCH':'main','RUN_PUBLIC_RETAIL':enabled}
        assert selected(public_rules,env)==wanted
    return {'offline_yaml_and_rules':'passed','workflow_cases':len(scenarios),'manual_public_cases':5,
            'artifact_allowlist':'passed','gitlab_server_ci_lint':False,'runner_execution':False}


if __name__=='__main__':
    print(json.dumps(validate(Path(__file__).resolve().parents[1]/'.gitlab-ci.yml'),indent=2))
