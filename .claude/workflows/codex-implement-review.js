export const meta = {
  name: 'codex-implement-review',
  description: 'Dynamic loop: Codex gpt-5.6-sol implements, Codex gpt-5.6-sol (xhigh) reviews; fix rounds until approved',
  whenToUse: 'Implement a change via Codex with adversarial Codex review. args: {task: "...", cwd?: "...", maxRounds?: 3}',
  phases: [
    { title: 'Implement', detail: 'Codex gpt-5.6-sol makes the change (workspace-write)' },
    { title: 'Review', detail: 'Codex gpt-5.6-sol at xhigh reasoning reviews the diff (read-only)' },
    { title: 'Fix', detail: 'Implementer Codex thread addresses findings; loops back to Review' },
  ],
}

const task = typeof args === 'string' ? args : (args && args.task)
if (!task) throw new Error('No task given. Invoke with args: {task: "what to implement"}')
const CWD = (args && args.cwd) || '/Users/carterhedrick/My Projects/Practical Rewards'
const MAX_ROUNDS = (args && Number(args.maxRounds)) || 3

const IMPL_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean', description: 'false only if the Codex call itself failed' },
    threadId: { type: 'string', description: 'threadId from the Codex tool result JSON; empty string if missing' },
    summary: { type: 'string', description: 'condensed report of what Codex says it did' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    error: { type: 'string', description: 'error text when ok=false, else empty' },
  },
  required: ['ok', 'threadId', 'summary', 'filesChanged'],
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['APPROVED', 'CHANGES_REQUIRED', 'REVIEW_FAILED'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: { file: { type: 'string' }, issue: { type: 'string' } },
        required: ['issue'],
      },
    },
    summary: { type: 'string', description: 'condensed review summary in the reviewer own words' },
  },
  required: ['verdict', 'findings', 'summary'],
}

const SCOPE_GUARD = `Orchestration infrastructure notice: files under .claude/ (workflows, settings, launch configs) belong to the orchestration harness running this loop, not to the task. They are intentional. Never modify, delete, review, or report on anything under .claude/ or on pre-existing untracked files you did not create. Additionally, the working tree may contain pre-existing uncommitted modifications from earlier, separately-approved tasks: these are intentional and final — build on top of them, never revert or remove them, and never treat their existence as a problem to fix.`

const RELAY_RULES = `You are a RELAY agent. Your only job is to drive the Codex CLI via its MCP tool and report back faithfully. Do NOT implement, review, or edit anything yourself with your own tools. The Codex tool result is JSON like {"threadId":"...","content":"..."} — capture both fields.`

const implementRelay = `${RELAY_RULES}

Steps:
1. Call ToolSearch with query "select:mcp__codex__codex" to load the Codex tool.
2. Call mcp__codex__codex with EXACTLY these parameters:
   - model: "gpt-5.6-sol"
   - cwd: ${JSON.stringify(CWD)}
   - sandbox: "workspace-write"
   - approval-policy: "never"
   - prompt: the text between CODEX_PROMPT_START and CODEX_PROMPT_END below, verbatim (markers excluded).
3. You may run "git status --porcelain" (Bash) in that directory to confirm which files changed.
4. Return StructuredOutput: ok=true, threadId, summary, filesChanged. If the Codex call errors, return ok=false with the error text in error.

CODEX_PROMPT_START
You are the implementer in an implement/review loop run by an orchestrator. Working directory: ${CWD}

${SCOPE_GUARD}

TASK:
${task}

Implement the task fully and directly in the working tree. Explore the repo first and match its existing conventions, style, and structure. Do not commit and do not create branches — leave the changes uncommitted. When finished, summarize exactly what you changed and list every file you touched.
CODEX_PROMPT_END`

function reviewRelay(round) {
  return `${RELAY_RULES}

Steps:
1. Call ToolSearch with query "select:mcp__codex__codex" to load the Codex tool.
2. Call mcp__codex__codex with EXACTLY these parameters:
   - model: "gpt-5.6-sol"
   - config: {"model_reasoning_effort": "xhigh"}
   - cwd: ${JSON.stringify(CWD)}
   - sandbox: "read-only"
   - approval-policy: "never"
   - prompt: the text between CODEX_PROMPT_START and CODEX_PROMPT_END below, verbatim (markers excluded).
3. Codex's reply ends with "VERDICT: APPROVED" or "VERDICT: CHANGES_REQUIRED". Transcribe its verdict and findings faithfully — do not add, drop, or soften anything. If the call fails or no verdict line is present, return verdict REVIEW_FAILED with the raw content in summary.

CODEX_PROMPT_START
You are an adversarial code reviewer (review round ${round}). Working directory: ${CWD}

${SCOPE_GUARD} Review ONLY whether the task below is implemented correctly — untracked files are outside your review entirely. Confine findings to actual defects in the task's implementation. The diff will also show pre-existing changes from earlier approved tasks; that is expected, is not a defect, and asking for those to be undone is not a valid finding.

The uncommitted working-tree changes implement this task:
${task}

Inspect the changes with "git status" and "git diff", and read any file you need (you are in a read-only sandbox). Review for: correctness bugs; broken HTML/CSS/JS or links; inconsistency with the task or with the rest of the codebase; incomplete implementation; unintended or unrelated edits to tracked files. Be adversarial but concrete: report only real issues that require a change, each with the file and exactly what to fix. No nitpicks or style preferences.

End your reply with exactly one line: "VERDICT: APPROVED" if the change is correct and complete, otherwise list numbered findings and end with "VERDICT: CHANGES_REQUIRED".
CODEX_PROMPT_END`
}

function fixRelay(findings, threadId, round) {
  const findingsText = findings
    .map((f, i) => `${i + 1}. ${f.file ? '[' + f.file + '] ' : ''}${f.issue}`)
    .join('\n')
  const routing = threadId
    ? `2. Call mcp__codex-reply — tool name mcp__codex__codex-reply — with threadId ${JSON.stringify(threadId)} and prompt: the text between CODEX_PROMPT_START and CODEX_PROMPT_END, verbatim (markers excluded).
3. If codex-reply fails (e.g. thread expired), fall back to a fresh mcp__codex__codex call with model "gpt-5.6-sol", cwd ${JSON.stringify(CWD)}, sandbox "workspace-write", approval-policy "never", and the same prompt.`
    : `2. Call mcp__codex__codex with model "gpt-5.6-sol", cwd ${JSON.stringify(CWD)}, sandbox "workspace-write", approval-policy "never", and prompt: the text between CODEX_PROMPT_START and CODEX_PROMPT_END, verbatim (markers excluded).`
  return `${RELAY_RULES}

Steps:
1. Call ToolSearch with query "select:mcp__codex__codex-reply,mcp__codex__codex" to load both Codex tools.
${routing}
4. You may run "git status --porcelain" (Bash) in ${JSON.stringify(CWD)} to confirm which files changed.
5. Return StructuredOutput: ok=true, threadId (from the result JSON), summary, filesChanged. If the call errors, return ok=false with the error text.

CODEX_PROMPT_START
Original task, for context: ${task}

${SCOPE_GUARD}

Reviewer findings from review round ${round} — fix them in the working tree now, with these hard limits: act only on findings about the task's own changes to tracked files. If a finding targets anything under .claude/, an untracked file, pre-existing uncommitted changes from earlier tasks, or anything else outside the task's scope, SKIP it — do not delete, revert, or modify that content under any circumstances — and note the skipped finding and why in your summary. Never delete files or revert pre-existing changes as a "fix".

FINDINGS:
${findingsText}

After fixing, summarize the fixes and list every file you touched. Do not commit.
CODEX_PROMPT_END`
}

log('Task: ' + task.slice(0, 140))
const impl = await agent(implementRelay, { label: 'codex-implement', phase: 'Implement', schema: IMPL_SCHEMA, effort: 'low' })
if (!impl || impl.ok === false) {
  return { status: 'implementation-failed', error: (impl && impl.error) || 'implementer relay returned nothing' }
}
let threadId = impl.threadId || ''
const files = new Set(impl.filesChanged || [])
const history = [{ stage: 'implement', summary: impl.summary }]

for (let round = 1; round <= MAX_ROUNDS; round++) {
  const review = await agent(reviewRelay(round), { label: 'codex-review-r' + round, phase: 'Review', schema: REVIEW_SCHEMA, effort: 'low' })
  if (!review || review.verdict === 'REVIEW_FAILED') {
    return { status: 'review-failed', round, detail: review ? review.summary : 'review relay returned nothing', filesChanged: [...files], history }
  }
  history.push({ stage: 'review-' + round, verdict: review.verdict, findings: review.findings, summary: review.summary })
  if (review.verdict === 'APPROVED') {
    log('Approved on review round ' + round)
    return { status: 'approved', reviewRounds: round, filesChanged: [...files], finalReview: review.summary, history }
  }
  log('Round ' + round + ': ' + review.findings.length + ' finding(s) — sending back to implementer')
  if (round === MAX_ROUNDS) {
    return { status: 'max-rounds-exhausted', reviewRounds: round, unresolvedFindings: review.findings, filesChanged: [...files], history }
  }
  const fix = await agent(fixRelay(review.findings, threadId, round), { label: 'codex-fix-r' + round, phase: 'Fix', schema: IMPL_SCHEMA, effort: 'low' })
  if (!fix || fix.ok === false) {
    return { status: 'fix-failed', round, error: (fix && fix.error) || 'fix relay returned nothing', unresolvedFindings: review.findings, filesChanged: [...files], history }
  }
  threadId = fix.threadId || threadId
  for (const f of fix.filesChanged || []) files.add(f)
  history.push({ stage: 'fix-' + round, summary: fix.summary })
}
