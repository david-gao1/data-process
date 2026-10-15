# 真实 Iceberg 的本机对照实验

```bash
uv venv experiments/iceberg/.venv
uv pip install --python experiments/iceberg/.venv/bin/python -r experiments/iceberg/requirements.lock.txt
experiments/iceberg/.venv/bin/python experiments/iceberg/poc.py
```

仅合成数据；临时目录自动清理。固定完整实验依赖在 requirements.lock.txt。检验 append / overwrite 两个 snapshot、历史读取、catalog 重开、DuckDB Arrow 内存桥接。不是原生 DuckDB Iceberg 扩展兼容测试，不是生产 catalog、并发或 out-of-core 性能测试。取舍见 [ADR](../../docs/adr/001-local-data-product.md)。
