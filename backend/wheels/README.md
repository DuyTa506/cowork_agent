Build inputs that are not on a package index. The Docker build installs `doccheck` from here
(`pip install --find-links /wheels`), so the system builds with no Internet access.

To upgrade doccheck, replace the wheel and update the version bound in `../requirements.txt`.

| Wheel | What | Source |
|---|---|---|
| `doccheck-*.whl` | format checker and document reader | built from the doccheck repository |
| `deepseek_harness_sdk-*.whl`, `deepseek_harness_runtime_bin-*.whl` | DeepSeek Harness: the agent loop behind the assistant (the second wheel is its ~95 MB runtime) | PyPI (pre-release `0.2.1rc2`), vendored so the image builds on the LAN |

The harness is pinned to an exact pre-release version; move it deliberately and rerun `tests/test_chat_api.py`.
