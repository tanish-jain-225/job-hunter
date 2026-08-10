
    let currentFilter = 'all';
    let cachedJobsMap = {};

    async function parseJsonResponse(res) {
      const text = await res.text();
      try {
        return JSON.parse(text);
      } catch (err) {
        if (!res.ok) {
          throw new Error(`Server returned HTTP ${res.status} (${res.statusText || 'Server Error'})`);
        }
        throw new Error(`Unexpected server response`);
      }
    }

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await parseJsonResponse(res);
        document.getElementById('metric-tracked').innerText = data.tracked ?? 0;
        document.getElementById('metric-emailed').innerText = data.emailed ?? 0;
        document.getElementById('metric-applied').innerText = data.applied ?? 0;
      } catch (err) {
        console.error('Failed to load stats', err);
      }
    }

    function switchTab(tab) {
      document.getElementById('tab-content-digest').style.display = tab === 'digest' ? 'block' : 'none';
      document.getElementById('tab-content-tracker').style.display = tab === 'tracker' ? 'block' : 'none';

      document.getElementById('tab-btn-digest').classList.toggle('active', tab === 'digest');
      document.getElementById('tab-btn-tracker').classList.toggle('active', tab === 'tracker');

      if (tab === 'tracker') {
        fetchAndRenderJobs();
      }
    }

    function setFilter(filter) {
      currentFilter = filter;
      document.querySelectorAll('.filter-pills .pill').forEach(el => el.classList.remove('active'));
      const pill = document.getElementById('pill-' + filter);
      if (pill) pill.classList.add('active');
      fetchAndRenderJobs();
    }

    async function fetchAndRenderJobs() {
      const container = document.getElementById('job-list-container');
      const search = document.getElementById('tracker-search-input').value.trim();

      try {
        const url = `/api/jobs?status=${encodeURIComponent(currentFilter)}&search=${encodeURIComponent(search)}`;
        const res = await fetch(url);
        const data = await parseJsonResponse(res);

        if (data.status !== 'success' || !data.jobs || data.jobs.length === 0) {
          container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted);">No matching jobs found in tracking store.</div>';
          return;
        }

        cachedJobsMap = {};
        data.jobs.forEach(j => { cachedJobsMap[j.job_id] = j; });

        container.innerHTML = data.jobs.map(j => {
          const score = j.score != null ? Number(j.score).toFixed(1) : 'N/A';
          const scoreClass = j.score >= 8.5 ? 'score-high' : (j.score >= 7.0 ? 'score-mid' : 'score-low');
          const isApplied = Boolean(j.applied);
          const hasDraft = j.draft && (j.draft.cover_note || j.draft.fit_summary);

          return `
            <div class="job-item">
              <div class="job-meta">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="job-title">${escapeHtml(j.title)}</span>
                  <span class="ats-tag">${escapeHtml(j.ats || 'ats')}</span>
                </div>
                <div class="job-sub">
                  <strong>${escapeHtml(j.company)}</strong> · ${escapeHtml(j.location || 'Remote/Unspecified')}
                  <span style="font-size:11px; color:var(--text-muted); margin-left:8px;">(${escapeHtml(j.job_id)})</span>
                </div>
                ${j.reason ? `<div class="job-reason">💡 ${escapeHtml(j.reason)}</div>` : ''}
              </div>
              <div class="job-actions">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="score-badge ${scoreClass}">${score}</span>
                  ${isApplied
                    ? `<button class="btn btn-secondary btn-sm btn-applied" title="Click to unmark applied" onclick="toggleAppliedDirect('${escapeHtml(j.job_id)}', 'unmark')">✓ Applied</button>`
                    : `<button class="btn btn-secondary btn-sm" onclick="toggleAppliedDirect('${escapeHtml(j.job_id)}', 'mark')">Mark Applied</button>`
                  }
                  <button class="btn btn-secondary btn-sm btn-danger" title="Delete job entry" onclick="deleteJobDirect('${escapeHtml(j.job_id)}')">🗑️ Delete</button>
                </div>
                <div style="display:flex; gap:6px;">
                  ${hasDraft ? `<button class="btn btn-secondary btn-sm" onclick="openKitModal('${escapeHtml(j.job_id)}')">Inspect Kit 📄</button>` : ''}
                  <a href="${escapeHtml(j.url)}" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration:none;">Open Link ↗</a>
                </div>
              </div>
            </div>
          `;
        }).join('');

      } catch (err) {
        container.innerHTML = `<div style="text-align:center; padding:40px; color:var(--danger);">Notice: ${escapeHtml(err.message)}</div>`;
      }
    }

    function openKitModal(jobId) {
      const j = cachedJobsMap[jobId];
      if (!j || !j.draft) return;

      document.getElementById('modal-job-title').innerText = j.title || 'Job Application Kit';
      document.getElementById('modal-job-meta').innerText = `${j.company} · ${j.location || 'Remote/Unspecified'}`;

      const d = j.draft;
      let html = '';

      if (d.fit_summary) {
        html += `<div class="kit-section"><div class="kit-label">Why It Fits</div><p style="font-size:13px; color:#334155; line-height:1.5;">${escapeHtml(d.fit_summary)}</p></div>`;
      }
      if (d.cover_note) {
        html += `
          <div class="kit-section">
            <div class="kit-label">Cover Note
              <button class="copy-btn" id="btn-copy-cover" onclick="copyCoverNote()">Copy Note 📋</button>
            </div>
            <div class="cover-box" id="cover-text">${escapeHtml(d.cover_note)}</div>
          </div>`;
      }
      if (d.tailored_bullets && d.tailored_bullets.length) {
        html += `<div class="kit-section"><div class="kit-label">Tailored Resume Bullets</div><ul style="padding-left:18px; font-size:13px; color:#334155;">${d.tailored_bullets.map(b => `<li style="margin-bottom:4px;">${escapeHtml(b)}</li>`).join('')}</ul></div>`;
      }
      if (d.gaps && d.gaps.length) {
        html += `<div class="kit-section"><div class="kit-label">Honest Gaps</div><ul style="padding-left:18px; font-size:13px; color:#334155;">${d.gaps.map(g => `<li style="margin-bottom:4px;">${escapeHtml(g)}</li>`).join('')}</ul></div>`;
      }
      if (d.questions_to_ask && d.questions_to_ask.length) {
        html += `<div class="kit-section"><div class="kit-label">Questions To Ask</div><ul style="padding-left:18px; font-size:13px; color:#334155;">${d.questions_to_ask.map(q => `<li style="margin-bottom:4px;">${escapeHtml(q)}</li>`).join('')}</ul></div>`;
      }

      html += `<div style="margin-top:20px; text-align:right;"><a href="${escapeHtml(j.url)}" target="_blank" class="btn btn-secondary btn-sm" style="display:inline-block; text-decoration:none;">Open Posting Page ↗</a></div>`;

      document.getElementById('modal-body').innerHTML = html;
      document.getElementById('kit-modal').classList.add('active');
    }

    function closeKitModal() {
      document.getElementById('kit-modal').classList.remove('active');
    }

    function copyCoverNote() {
      const txt = document.getElementById('cover-text').innerText;
      navigator.clipboard.writeText(txt).then(() => {
        const btn = document.getElementById('btn-copy-cover');
        btn.innerText = 'Copied! ✓';
        setTimeout(() => { btn.innerText = 'Copy Note 📋'; }, 2000);
      });
    }

    async function runPipeline() {
      const btn = document.getElementById('btn-run');
      const spinner = document.getElementById('run-spinner');
      const text = document.getElementById('run-text');
      const consoleBox = document.getElementById('run-console');
      const isMock = false;

      btn.disabled = true;
      spinner.style.display = 'block';
      text.innerText = 'Hunting Jobs...';
      consoleBox.innerText = `Starting pipeline execution...
[1/5] Scanning ATS endpoints...
[2/5] Filtering candidate matches...`;

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mock: isMock })
        });
        const data = await parseJsonResponse(res);
        if (data.status === 'success') {
          consoleBox.innerText = `✅ ${data.message}
Digest generated & tracking store updated!`;
          refreshDigest();
          loadStats();
          fetchAndRenderJobs();
        } else {
          consoleBox.innerText = '❌ Error: ' + (data.message || 'Pipeline failed');
        }
      } catch (err) {
        consoleBox.innerText = '❌ Notice: ' + err.message;
      } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
        text.innerText = 'Run Job Hunt Now';
      }
    }

    async function toggleAppliedDirect(jobId, action) {
      try {
        const res = await fetch('/api/applied', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId, action: action })
        });
        const data = await parseJsonResponse(res);
        if (data.status === 'success') {
          loadStats();
          fetchAndRenderJobs();
          refreshDigest();
        } else {
          alert('Notice: ' + data.message);
        }
      } catch (err) {
        alert('Notice: ' + err.message);
      }
    }

    async function deleteJobDirect(jobId) {
      if (!confirm(`Are you sure you want to delete job '${jobId}' from tracking store?`)) {
        return;
      }
      try {
        const res = await fetch('/api/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId })
        });
        const data = await parseJsonResponse(res);
        if (data.status === 'success') {
          loadStats();
          fetchAndRenderJobs();
          refreshDigest();
        } else {
          alert('Notice: ' + data.message);
        }
      } catch (err) {
        alert('Notice: ' + err.message);
      }
    }

    async function markAppliedFromInput(action) {
      const txt = document.getElementById('txt-job-id');
      const status = document.getElementById('applied-status');
      const jobId = txt.value.trim();
      if (!jobId) {
        status.innerText = 'Please enter a valid Job ID.';
        return;
      }

      try {
        const res = await fetch('/api/applied', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId, action: action || 'mark' })
        });
        const data = await parseJsonResponse(res);
        if (data.status === 'success') {
          status.innerText = '✅ ' + data.message;
          txt.value = '';
          loadStats();
          fetchAndRenderJobs();
          refreshDigest();
        } else {
          status.innerText = '❌ ' + data.message;
        }
      } catch (err) {
        status.innerText = '❌ Notice: ' + err.message;
      }
    }

    async function addCustomJobFromInput() {
      const titleEl = document.getElementById('add-title');
      const companyEl = document.getElementById('add-company');
      const locEl = document.getElementById('add-location');
      const urlEl = document.getElementById('add-url');
      const scoreEl = document.getElementById('add-score');
      const appliedEl = document.getElementById('add-applied');
      const status = document.getElementById('add-job-status');

      const title = titleEl.value.trim();
      const company = companyEl.value.trim();

      if (!title || !company) {
        status.innerText = 'Please enter both Job Title and Company.';
        return;
      }

      status.innerText = 'Adding job...';

      try {
        const res = await fetch('/api/jobs/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title,
            company: company,
            location: locEl.value.trim() || 'Remote/Unspecified',
            url: urlEl.value.trim() || '#',
            score: parseFloat(scoreEl.value) || 8.0,
            applied: appliedEl.checked
          })
        });
        const data = await parseJsonResponse(res);
        if (data.status === 'success') {
          status.innerText = '✅ ' + data.message;
          titleEl.value = '';
          companyEl.value = '';
          locEl.value = '';
          urlEl.value = '';
          appliedEl.checked = false;
          loadStats();
          fetchAndRenderJobs();
          refreshDigest();
        } else {
          status.innerText = '❌ ' + data.message;
        }
      } catch (err) {
        status.innerText = '❌ Notice: ' + err.message;
      }
    }

    function refreshDigest() {
      const frame = document.getElementById('digest-frame');
      frame.src = '/api/digest?t=' + new Date().getTime();
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    // Initial load
    loadStats();
  