mkdir -p .tmp
uv sync --no-default-groups
uv pip list --format json > ./.tmp/package-list.json
uv sync --no-default-groups --group license
uv run pip-licenses --format=json --no-version --output-file=./.tmp/licenses.json --with-license-file --with-notice-file
uv run scripts/parse_licenses.py
uv sync
copy .\.tmp\NOTICE.md .\NOTICE /Y
copy .\.tmp\THIRD_PARTY_LICENSES.md .\THIRD_PARTY_LICENSES.md /Y
