'use strict';

const scenarios = {
  mcp: {
    file: 'tools.py', lane: 'MCP server', label: 'excessive_tool_scope',
    before: '@mcp.tool()\ndef run_command(command: str):\n    return subprocess.run(\n        command, shell=True,\n        capture_output=True\n    )',
    after: '@mcp.tool()\ndef get_order_status(order_id: str):\n    validate_order_id(order_id)\n    require_order_access(order_id)\n    return orders.lookup(order_id)',
    initial: 'The agent is about to expose a shell command as a tool. Run the example check to see the finding.',
    blocked: 'An unrestricted shell tool gives the caller broad execution scope. Repair hint: expose one narrow operation, validate inputs, and enforce access checks.',
    passed: 'The revised example exposes one operation and explicit checks. This walkthrough returns no finding; it does not establish that the surrounding application is secure.'
  },
  sql: {
    file: 'login.php', lane: 'Web / PHP', label: 'sql_injection',
    before: '<?php\n$id = $_GET["id"];\n$query = "SELECT * FROM users\n          WHERE id = " . $id;\n$result = mysqli_query($db, $query);',
    after: '<?php\n$stmt = $db->prepare(\n    "SELECT * FROM users WHERE id = ?"\n);\n$stmt->bind_param("i", $id);\n$stmt->execute();',
    initial: 'The proposed query concatenates a request parameter into SQL. Run the example check to inspect the pattern.',
    blocked: 'User-controlled text is concatenated into a SQL statement. Repair hint: use a parameterised query and validate the expected input type.',
    passed: 'The revised example uses a bound parameter. The scripted check returns no finding for this pattern. Authentication, authorisation and the wider application still need review.'
  },
  wrapper: {
    file: 'orders.py', lane: 'Team policy · product thesis', label: 'reviewer_correction',
    before: 'from company.db import safe_query\n\ndef order_summary(order_id):\n    return safe_query(\n        "orders.by_id",\n        {"order_id": order_id}\n    )',
    after: '# Reviewer-validated reference example\n# safe_query binds values internally.\nfrom company.db import safe_query\n\ndef order_summary(order_id):\n    return safe_query(\n        "orders.by_id", {"order_id": order_id}\n    )',
    initial: 'A generic reviewer may misunderstand an internal wrapper. Explore how a reviewer correction would become a labelled reference example.',
    blocked: 'Reviewer correction: this approved wrapper binds values internally. Keep the code, correct the finding, and reserve different wrapper examples to test generalisation.',
    passed: 'The correction is represented as a validated reference example. Actual submission, adapter training and serving are not performed by this walkthrough or connected in the prototype.'
  }
};
let currentScenario = 'mcp';
let step = 0;
const $ = (selector) => document.querySelector(selector);
const codeElement = $('#demo-code');
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function showCode(code) {
  codeElement.innerHTML = code.split('\n').map((line, index) => '<span class="line-number">' + String(index + 1).padStart(2, '0') + '</span>' + escapeHTML(line)).join('\n');
}

function renderDemo() {
  const example = scenarios[currentScenario];
  $('#demo-file').textContent = example.file;
  $('#demo-lane').textContent = example.lane;
  $('#demo-version').textContent = step === 2 ? (currentScenario === 'wrapper' ? 'CORRECTED REFERENCE' : 'REVISED WRITE') : 'PROPOSED WRITE';
  $('#demo-agent').textContent = currentScenario === 'wrapper' ? 'PRODUCT THESIS → ILLUSTRATIVE EXAMPLE' : 'CLAUDE CODE → PRETOOLUSE';
  showCode(step === 2 ? example.after : example.before);
  const status = $('#decision-status');
  status.className = 'decision-status' + (step === 1 ? ' blocked' : step === 2 ? ' passed' : '');
  status.innerHTML = '<span class="decision-symbol">' + (step === 0 ? '↗' : step === 1 ? '!' : '✓') + '</span><h3>' + (step === 0 ? 'Ready to inspect.' : step === 1 ? (currentScenario === 'wrapper' ? 'Teach the exception.' : 'Write blocked.') : (currentScenario === 'wrapper' ? 'Correction captured.' : 'No finding.')) + '</h3>';
  $('#decision-copy').textContent = step === 0 ? example.initial : step === 1 ? example.blocked : example.passed;
  $('#inspector-rule > span').textContent = step === 0 ? 'LANE' : 'LABEL';
  $('#demo-lane').textContent = step === 0 ? example.lane : (step === 1 ? example.label : currentScenario === 'wrapper' ? 'validated_reference' : 'none');
  const labels = currentScenario === 'wrapper' ? ['Review the example', 'Apply reviewer correction', 'Replay walkthrough'] : ['Run example check', 'Show the agent’s repair', 'Replay walkthrough'];
  $('#demo-run').innerHTML = escapeHTML(labels[step]) + ' <span aria-hidden="true">' + (step === 2 ? '↺' : '→') + '</span>';
  $('#demo-footnote').textContent = currentScenario === 'wrapper' ? 'Product thesis illustration. No correction is submitted and no model update is triggered.' : 'Scripted walkthrough. No live API request or security verdict is generated.';
  document.querySelectorAll('[data-step]').forEach((el) => el.classList.toggle('active', Number(el.dataset.step) === step));
}
document.querySelectorAll('[data-scenario]').forEach((button) => {
  button.addEventListener('click', () => {
    currentScenario = button.dataset.scenario;
    step = 0;
    document.querySelectorAll('[data-scenario]').forEach((tab) => {
      const selected = tab === button;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    $('#scenario-panel').setAttribute('aria-labelledby', button.id);
    renderDemo();
  });
  button.addEventListener('keydown', (event) => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll('[data-scenario]')];
    const index = tabs.indexOf(button);
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    tabs[nextIndex].click();
    tabs[nextIndex].focus();
  });
});
$('#demo-run').addEventListener('click', () => { step = (step + 1) % 3; renderDemo(); });
$('#demo-reset').addEventListener('click', () => { step = 0; renderDemo(); });

const nodes = {
  agent: ['Implemented', 'Intercept the proposed change', 'Claude Code triggers the hook before supported write and edit operations. The guard inspects code in its configured scope; this is a development checkpoint, not a repository-wide audit.'],
  hook: ['Implemented', 'Route the check. Catch secrets locally.', 'The hook checks the configured path and routes by file type and imports. A local secret pattern match blocks the write without a model call. Otherwise, the classifier receives a bounded code snippet.'],
  mubit: ['Implemented', 'Keep the provider call. Capture the task.', 'Each security lane uses stable instructions. Classifier calls go through the Mubit gateway, where recorded examples can be grouped into recurring tasks. The current application still uses the configured provider model.'],
  provider: ['Implemented', 'A focused classification request', 'The current configuration calls Claude Haiku through the Mubit Anthropic route. The classifier requests one lane-specific label. A provider answer is a judgement to evaluate, not independent proof of a vulnerability.'],
  decision: ['Implemented', 'Return a finding and a repair hint', 'A finding blocks the supported write and returns a fixed repair hint to the agent. No finding allows it. The prototype also allows writes on errors, budget exhaustion, and after three blocks on a file. Decisions are logged locally.'],
  correction: ['Local only', 'Store the reviewer’s correction', 'The feedback script records the original finding and corrected label in a local file. Submission to Mubit is a stub. Connecting validated corrections to training is a required next step.'],
  adapter: ['Planned integration', 'Train, compare, then earn production use', 'Mubit documents task-specific adapter training and hosted comparison. VulHawk has not connected corrected examples or production adapter inference. Evaluate missed findings, false alarms, latency and cost before replacing the provider path.']
};
document.querySelectorAll('[data-node]').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('[data-node]').forEach((node) => {
      const selected = node === button;
      node.setAttribute('aria-pressed', String(selected));
      node.classList.toggle('selected', selected);
    });
    const [status, title, description] = nodes[button.dataset.node];
    $('#arch-status').textContent = status;
    $('#arch-status').className = 'pill ' + (status === 'Implemented' ? 'pill-green' : 'pill-orange');
    $('#arch-title').textContent = title;
    $('#arch-description').textContent = description;
  });
});

const pounds = new Intl.NumberFormat('en-GB', {style:'currency',currency:'GBP',maximumFractionDigits:0});
function calculate() {
  const developers = Number($('#developers').value);
  const minutes = Number($('#minutes').value);
  const rate = Number($('#rate').value);
  const hours = developers * minutes * 22 / 60;
  $('#developers-value').textContent = developers;
  $('#minutes-value').textContent = minutes + ' min';
  $('#rate-value').textContent = pounds.format(rate);
  $('#calc-value').textContent = pounds.format(hours * rate);
  $('#calc-hours').textContent = hours.toFixed(1) + ' hours returned';
}
['developers','minutes','rate'].forEach((id) => $('#' + id).addEventListener('input', calculate));

const slides = [
  {kicker:'01 / THE PROBLEM',title:'Code at agent speed.<br><span class="serif">Review at human speed.</span>',copy:'Coding agents can produce changes faster than a team can review them. Repeated security mistakes consume the same senior attention, again and again.',note:'The initial customer: a small engineering team already shipping with coding agents.'},
  {kicker:'02 / THE PRODUCT',title:'Catch the risk.<br><span class="serif">Give the agent a fix.</span>',copy:'VulHawk checks proposed writes inside Claude Code. A focused finding blocks the write and sends back a repair instruction, while the agent is still working.',note:'Built: scoped hook, lane classification through Mubit, repair hints and local decision logs.'},
  {kicker:'03 / WHY MUBIT',title:'Turn repeated checks<br><span class="serif">into a specialist.</span>',copy:'The thesis: capture recurring security decisions, validate reviewer corrections, and use them to train a narrow model that understands a team’s rules.',note:'Planned integration: correction submission and production adapter serving. Learning is not yet proven.'},
  {kicker:'04 / THE COMMERCIAL CASE',title:'Start with one repo.<br><span class="serif">Earn the team rollout.</span>',copy:'Target engineering leads building agent and MCP products. Sell shared policy, review history and controls through a team subscription, with transparent model usage.',note:'Business model hypothesis. Validate willingness to pay through repository pilots.'},
  {kicker:'05 / THE PROOF',title:'Fewer false alarms.<br><span class="serif">No hidden trade-offs.</span>',copy:'Measure useful findings, missed vulnerabilities, repair acceptance, check delay and cost. Show a correction improving fresh cases before replacing the provider model.',note:'Provider evaluation and adapter evaluation are separate. Compare at the same task budget.'},
  {kicker:'06 / THE ASK',title:'Bring one repository.<br><span class="serif">Teach us your rules.</span>',copy:'We’re looking for pilot teams using coding agents. Start with one risky workflow and agree what a useful review must do.',note:'VulHawk · Catch. Repair. Specialise. · Night Shift × Mubit, October 2026'}
];
let slideIndex = 0;
function renderSlide() {
  const slide = slides[slideIndex];
  $('#pitch-count').textContent = String(slideIndex + 1).padStart(2,'0') + ' / 06';
  $('#pitch-slide').innerHTML = '<div class="eyebrow">' + slide.kicker + '</div><h2>' + slide.title + '</h2><p>' + slide.copy + '</p><p class="slide-note">' + slide.note + '</p>';
  $('#pitch-prev').disabled = slideIndex === 0;
  $('#pitch-next').disabled = slideIndex === slides.length - 1;
}
document.querySelectorAll('[data-open-pitch]').forEach((button) => button.addEventListener('click', () => {slideIndex = 0; renderSlide(); $('#pitch-dialog').showModal();}));
$('#pitch-prev').addEventListener('click', () => {slideIndex = Math.max(0,slideIndex - 1);renderSlide();});
$('#pitch-next').addEventListener('click', () => {slideIndex = Math.min(slides.length - 1,slideIndex + 1);renderSlide();});
$('#pitch-dialog').addEventListener('keydown', (event) => {
  if(event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault();
    slideIndex = Math.max(0,Math.min(slides.length - 1,slideIndex + (event.key === 'ArrowRight' ? 1 : -1)));
    renderSlide();
  }
});
document.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => $('#' + button.dataset.close).close()));
$('#pilot-open').addEventListener('click', () => $('#pilot-dialog').showModal());
document.querySelectorAll('dialog').forEach((dialog) => dialog.addEventListener('click', (event) => {
  if(event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if(event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
}));

$('#pilot-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const team = $('#pilot-team').value.trim() || 'Our team';
  const focus = $('#pilot-focus').value;
  const measures = [...$('#pilot-form').querySelectorAll('fieldset label')].filter((label) => label.querySelector('input').checked).map((label) => '- ' + label.textContent.trim());
  const brief = 'VULHAWK — REPOSITORY PILOT\n\nTeam: ' + team + '\nFocus: ' + focus + '\n\n1. Pick one repository and a bounded review scope.\n2. Agree expected labels with a human reviewer.\n3. Reserve fresh cases before collecting training examples.\n4. Review findings and repair suggestions in the coding workflow.\n5. Compare against the team’s baseline.\n\nSUCCESS MEASURES\n' + (measures.join('\n') || '- Agree success measures with your team.') + '\n\nLEARNING THESIS\nConnect validated reviewer corrections to Mubit adapter training; evaluate missed findings, false alarms, latency and cost before using a specialist in production.\n\nCURRENT LIMITS\nPrototype checks are scoped and allow writes on provider failure, budget exhaustion, and after three blocks per file. Corrections are local; adapter feedback and production inference are not connected.\n\nSource: https://github.com/keerthanenr/mubit-sec-guard\n';
  const url = URL.createObjectURL(new Blob([brief], {type:'text/plain;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;link.download = 'vulhawk-pilot-brief.txt';document.body.appendChild(link);link.click();link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  $('#pilot-confirmation').textContent = 'Your pilot brief is ready. The download was requested; no information was sent to a server.';
});

renderDemo();
calculate();
