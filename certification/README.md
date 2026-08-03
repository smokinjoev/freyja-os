# Certification Framework

The Certification Framework validates Freyja's planner, tools, memory, connectors, honesty, and future Chaos Mode.

Run the default smoke suite with the default Ollama provider:

```bash
freyja-certify
```

Useful options:

```bash
freyja-certify --list-suites
freyja-certify honesty --model qwen2.5:7b
freyja-certify planner --router-mode local --output-dir certification/reports
```

Reports are written to `certification/reports/` by default as both Markdown and JSON with timestamped filenames. Each report records the timestamp, git SHA, branch, working-tree state, hostname, provider, model, router mode, suite name, overall score, execution time, and certification CLI version.
