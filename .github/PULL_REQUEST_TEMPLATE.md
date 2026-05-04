## Summary
- 

## Linked Issues
- Closes #

## Verification
- [ ] `python3 -m py_compile $(rg --files src -g '*.py')`
- [ ] `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- [ ] `scripts/regression_checks.sh`
- [ ] `scripts/failure_matrix.sh`
- [ ] `scripts/acceptance_checks.sh`

## Checklist
- [ ] Milestone/branch strategy followed (`codex/m*`, `codex/m*-*`)
- [ ] Status labels updated (`status:in-progress` -> close)
- [ ] Docs updated if behavior changed
