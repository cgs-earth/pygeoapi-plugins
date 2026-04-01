# install dependencies
# this project uses uv to manage dependencies
deps:
	uv sync --all-groups --locked --all-extras

test:
	# run tests in parallel with pytest-xdist and stop after first failure; run in verbose mode and show durations of the 5 slowest tests
	uv run pyright && uv run pytest -n 20 -x --maxfail=1 -vv --durations=5 -m "not upstream"

clean:
	rm -rf .venv/
	rm -rf .pytest_cache/