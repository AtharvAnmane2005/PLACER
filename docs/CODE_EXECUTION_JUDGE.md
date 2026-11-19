# Code execution and the isolated judge

## One implementation

`backend/app/services/code_execution_service.py` exposes the only public
interface:

```python
execute_code(language, code, test_cases, only_visible=False) -> CodeRunSummary
```

`CODE_EXECUTION_BACKEND` selects where the subprocess runs:

| Value | Behaviour |
| --- | --- |
| `local` (default) | Runs in the backend host process tree. Intended for development and tests. |
| `judge` | POSTs the submission to the judge service. The backend never spawns student code. |

`docker-compose.yml` sets `judge` for the backend and `local` inside the
judge. The judge imports the backend's own runner and models (only the modules
that runner needs are copied into the image), so grading logic is not
duplicated.

## Security boundary

The judge container is the boundary, not the Python code:

* `read_only: true` root filesystem;
* `tmpfs /tmp` only (64 MB, `nosuid`, `nodev`);
* non-root user (uid 10001);
* `cap_drop: ALL`, `no-new-privileges`;
* `pids_limit: 128`, `mem_limit: 256m`, `cpus: 1.0`;
* attached only to the internal `judge_net` network, with no published port;
* a bounded semaphore returns `503` under overload instead of queuing.

The shared runner additionally applies a language allowlist (Python,
JavaScript), per-test and total timeouts, a minimal environment, a fresh
temporary working directory, code-size and output-size limits, and
`python -I`.

## Hidden test cases

The judge receives every test case because it must grade hidden tests. The
shared runner returns `input`, `expected_output` and `actual_output` only for
non-hidden cases; hidden results carry pass/fail and status only. The student
projection (`QuestionStudentView.visible_test_cases`) exposes exactly the
non-hidden samples.

Reference solutions are executed once at seed time to produce expected outputs
and are never written to MongoDB.

## Verifying locally

```powershell
# Build and run the judge with the same limits as compose
docker compose build judge
docker run -d --name placer_judge_test -p 18080:8080 `
  --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m `
  --cap-drop ALL --security-opt no-new-privileges:true `
  --pids-limit 128 --memory 256m --cpus 1 placer-judge

# Point a host backend at it
$env:CODE_EXECUTION_BACKEND="judge"
$env:CODE_EXECUTION_JUDGE_URL="http://localhost:18080"
```

`GET /health` returns the supported languages. `POST /run` accepts
`{language, code, test_cases, only_visible}` and returns the same
`CodeRunSummary` shape as the local runner.
