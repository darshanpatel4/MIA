/**
 * MIA Skills Module
 * Lists installed agent skills (data/skills/<skill_name>/SKILL.md).
 */

let allSkills = [];

async function loadSkills() {
    const grid = document.getElementById('skillsGrid');
    try {
        if (grid && allSkills.length === 0) {
            grid.innerHTML = '<p style="color:var(--text-dim);">Loading skills...</p>';
        }

        const res = await apiFetch('/api/skills');

        if (Array.isArray(res)) {
            allSkills = res;
            renderSkills(allSkills);
        } else {
            console.error('Invalid response:', res);
            if (grid) grid.innerHTML = `<p style="color:var(--danger);">Error: ${res.detail || 'Invalid format'}</p>`;
        }
    } catch (e) {
        console.error('Failed to load skills:', e);
        if (grid) grid.innerHTML = `<p style="color:var(--danger);">Failed to load skills: ${e.message}</p>`;
    }
}

function searchSkills(query) {
    const q = query.toLowerCase();
    const filtered = allSkills.filter(s =>
        s.name.toLowerCase().includes(q) ||
        (s.description || '').toLowerCase().includes(q)
    );
    renderSkills(filtered);
}

function renderSkills(skills) {
    const grid = document.getElementById('skillsGrid');
    if (!grid) return;

    if (skills.length === 0) {
        grid.innerHTML = `
            <p style="color:var(--text-dim); grid-column: 1 / -1;">No skills found.</p>
        `;
        return;
    }

    grid.innerHTML = skills.map(skill => `
        <div class="stat-card">
            <div class="stat-card-header">
                <span class="stat-card-title">${escapeHtml(skill.name)}</span>
                <span class="stat-card-icon">${ICON.puzzle}</span>
            </div>
            <div class="stat-card-sub" style="margin-top: 8px;">${escapeHtml(skill.description || 'No description available.')}</div>
        </div>
    `).join('');
}
