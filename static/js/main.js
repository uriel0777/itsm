document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const ticketsList = document.getElementById('ticketsList');
    const searchInput = document.getElementById('searchInput');
    const filterAssignee = document.getElementById('filterAssignee');
    const filterStatus = document.getElementById('filterStatus');
    const filterTag = document.getElementById('filterTag');

    const ticketModal = document.getElementById('ticketModal');
    const ticketForm = document.getElementById('ticketForm');
    const titleInput = document.getElementById('title');
    const descInput = document.getElementById('description');
    const priorityInput = document.getElementById('priority');
    const assigneeInput = document.getElementById('assignee');
    const statusInput = document.getElementById('status');
    const taskTypeInput = document.getElementById('task_type');
    const dueDateInput = document.getElementById('due_date');
    const tagsInput = document.getElementById('tags');
    const statusGroup = document.getElementById('statusGroup');
    const ticketIdInput = document.getElementById('ticketId');

    let allTickets = [], systemUsers = [], systemTags = [], systemSettings = {};

    // Theme Toggle
    const themeBtn = document.getElementById('themeToggleBtn');
    if (themeBtn) {
        if (localStorage.getItem('theme') === 'light') document.body.classList.add('light-theme');
        themeBtn.addEventListener('click', () => {
            document.body.classList.toggle('light-theme');
            localStorage.setItem('theme', document.body.classList.contains('light-theme') ? 'light' : 'dark');
        });
    }

    // Init Data
    async function initData() {
        try {
            const [usersRes, tagsRes, settingsRes, ticketsRes] = await Promise.all([
                fetch('/api/users'), fetch('/api/tags'), fetch('/api/settings'), fetch('/api/tickets')
            ]);
            
            systemUsers = await usersRes.json();
            systemTags = await tagsRes.json();
            systemSettings = await settingsRes.json();
            allTickets = await ticketsRes.json();
            
            populateDropdowns();
            renderTickets();
            updateStats();
        } catch (err) { console.error('Error init data', err); }
    }

    function populateDropdowns() {
        const createOption = (v, t) => `<option value="${v}">${t}</option>`;
        
        let uOps = createOption("", "Unassigned");
        systemUsers.forEach(u => uOps += createOption(u.id, u.name || u.email.split('@')[0]));
        assigneeInput.innerHTML = uOps;
        filterAssignee.innerHTML = createOption("", "All Assignees") + createOption("Unassigned", "Unassigned") + 
                                   systemUsers.map(u => createOption(u.id, u.name || u.email.split('@')[0])).join('');
                                   
        let tOps = "";
        systemTags.forEach(t => tOps += createOption(t.id, t.name));
        tagsInput.innerHTML = tOps;
        filterTag.innerHTML = createOption("", "All Tags") + systemTags.map(t => createOption(t.id, t.name)).join('');
    }

    async function reloadTickets() {
        allTickets = await (await fetch('/api/tickets')).json();
        renderTickets();
        updateStats();
    }

    // SLA
    function getSLAStatus(createdAt, priority, status) {
        if (status === 'Resolved') return { text: 'Resolved', class: 'sla-good' };
        
        const diffHours = (new Date().getTime() - new Date(createdAt).getTime()) / (1000 * 60 * 60);
        
        const targetMap = {
            'Critical': parseFloat(systemSettings.sla_critical_hours) || 1,
            'High': parseFloat(systemSettings.sla_high_hours) || 4,
            'Medium': parseFloat(systemSettings.sla_medium_hours) || 24,
            'Low': parseFloat(systemSettings.sla_low_hours) || 48
        };
        const target = targetMap[priority] || 24;
        
        if (diffHours >= target) return { text: `Breached (${target}h)`, class: 'sla-bad' };
        if (diffHours >= target * 0.75) return { text: `At Risk (<${Math.ceil(target - diffHours)}h)`, class: 'sla-warn' };
        return { text: `On Target (${Math.ceil(target - diffHours)}h)`, class: 'sla-good' };
    }

    function renderTickets() {
        if (!ticketsList) return;
        const sTerm = searchInput ? searchInput.value.toLowerCase() : '';
        const fAssig = filterAssignee ? filterAssignee.value : '';
        const fStat = filterStatus ? filterStatus.value : '';
        const fTag = filterTag ? filterTag.value : '';

        const filtered = allTickets.filter(t => {
            const mSearch = t.title.toLowerCase().includes(sTerm) || (t.description || '').toLowerCase().includes(sTerm);
            const mAssig = fAssig ? (fAssig === 'Unassigned' ? !t.assignee_id : t.assignee_id == fAssig) : true;
            const mStat = fStat ? t.status === fStat : true;
            const mTag = fTag ? t.tags.some(tag => tag.id == fTag) : true;
            return mSearch && mAssig && mStat && mTag;
        });

        ticketsList.innerHTML = '';
        filtered.forEach(t => {
            const sla = getSLAStatus(t.created_at, t.priority, t.status);
            const assigHtml = t.assignee || '<span style="color:var(--text-muted);font-style:italic;">Unassigned</span>';
            const tagsHtml = t.tags.map(tag => `<span class="badge" style="background:${tag.color}20;color:${tag.color};border:1px solid ${tag.color};font-size:0.7rem">${tag.name}</span>`).join(' ');
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>#${t.id}</td>
                <td><strong style="display:block;margin-bottom:0.25rem">${t.title}</strong>${tagsHtml}</td>
                <td><span style="display:block;font-size:0.85rem">${t.task_type}</span><small style="color:var(--text-muted)">Due: ${t.due_date||'N/A'}</small></td>
                <td><span class="badge priority-${t.priority}">${t.priority}</span></td>
                <td><span class="badge status-${t.status.replace(' ', '-')}">${t.status}</span></td>
                <td>${assigHtml}</td>
                <td class="${sla.class}"><i class="fa-solid fa-clock"></i> ${sla.text}</td>
                <td>
                    <button class="action-btn edit-btn" data-id="${t.id}"><i class="fa-solid fa-pen-to-square"></i></button>
                    ${t.status !== 'Resolved' ? `<button class="action-btn resolve-btn" data-id="${t.id}"><i class="fa-solid fa-check"></i></button>` : ''}
                </td>
            `;
            ticketsList.appendChild(tr);
        });

        document.querySelectorAll('.edit-btn').forEach(b => b.addEventListener('click', e => openModal(allTickets.find(t => t.id == e.currentTarget.dataset.id))));
        document.querySelectorAll('.resolve-btn').forEach(b => b.addEventListener('click', e => updateTicket(e.currentTarget.dataset.id, { status: 'Resolved' })));
    }

    function updateStats() {
        if (!document.getElementById('statTotal')) return;
        document.getElementById('statTotal').textContent = allTickets.length;
        document.getElementById('statInProgress').textContent = allTickets.filter(t => t.status === 'In Progress').length;
        document.getElementById('statHighPriority').textContent = allTickets.filter(t => t.priority === 'High' || t.priority === 'Critical').length;
        document.getElementById('statResolved').textContent = allTickets.filter(t => t.status === 'Resolved').length;
    }

    // Date Picker Logic
    function updateDateEnforcement() {
        if(!dueDateInput) return;
        const now = new Date();
        const type = taskTypeInput.value;
        const minDate = new Date();
        const maxDate = new Date();

        if (type === 'Short-term') {
            minDate.setDate(now.getDate());
            maxDate.setDate(now.getDate() + 7);
        } else {
            minDate.setDate(now.getDate() + 8);
            maxDate.setDate(now.getDate() + 60);
        }
        
        dueDateInput.min = minDate.toISOString().split('T')[0];
        dueDateInput.max = maxDate.toISOString().split('T')[0];
        
        // Reset if invalid
        if(dueDateInput.value) {
            const v = new Date(dueDateInput.value);
            if(v < minDate || v > maxDate) dueDateInput.value = '';
        }
    }
    
    if(taskTypeInput) taskTypeInput.addEventListener('change', updateDateEnforcement);

    // Modal
    function openModal(data = null) {
        ticketModal.classList.add('active');
        if (data) {
            document.getElementById('modalTitle').textContent = 'Edit Task #' + data.id;
            ticketIdInput.value = data.id;
            titleInput.value = data.title;
            descInput.value = data.description || '';
            priorityInput.value = data.priority;
            assigneeInput.value = data.assignee_id || '';
            taskTypeInput.value = data.task_type || 'Short-term';
            updateDateEnforcement();
            dueDateInput.value = data.due_date || '';
            statusGroup.style.display = 'block';
            statusInput.value = data.status;
            
            // Set multi select
            Array.from(tagsInput.options).forEach(opt => {
                opt.selected = data.tags.some(t => t.id == opt.value);
            });
        } else {
            document.getElementById('modalTitle').textContent = 'Create New Task';
            ticketForm.reset();
            ticketIdInput.value = '';
            statusGroup.style.display = 'none';
            statusInput.value = 'New';
            taskTypeInput.value = 'Short-term';
            updateDateEnforcement();
        }
    }

    document.querySelectorAll('.closeModalBtn').forEach(b => b.addEventListener('click', () => ticketModal.classList.remove('active')));
    const a = document.getElementById('newTicketBtn'), b = document.getElementById('headerNewTicketBtn');
    if(a) a.addEventListener('click', e => { e.preventDefault(); openModal(); });
    if(b) b.addEventListener('click', e => { e.preventDefault(); openModal(); });

    // Ticket Save
    if (ticketForm) {
        ticketForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const selectedTags = Array.from(tagsInput.selectedOptions).map(o => parseInt(o.value));
            
            const payload = {
                title: titleInput.value,
                description: descInput.value,
                priority: priorityInput.value,
                assignee_id: assigneeInput.value || null,
                task_type: taskTypeInput.value,
                due_date: dueDateInput.value,
                tag_ids: selectedTags
            };
            if (statusGroup.style.display !== 'none') payload.status = statusInput.value;

            const id = ticketIdInput.value;
            await fetch(id ? `/api/tickets/${id}` : '/api/tickets', {
                method: id ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            ticketModal.classList.remove('active');
            reloadTickets();
        });
    }

    async function updateTicket(id, payload) {
        await fetch(`/api/tickets/${id}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        reloadTickets();
    }

    // Filter Listeners
    if(searchInput) searchInput.addEventListener('input', renderTickets);
    if(filterAssignee) filterAssignee.addEventListener('change', renderTickets);
    if(filterStatus) filterStatus.addEventListener('change', renderTickets);
    if(filterTag) filterTag.addEventListener('change', renderTickets);

    initData();
});
