/**
 * static/js/app.js — AI SMS Engine Dashboard
 */
const API = '';
let activeBusiness = null;
let activeThreadId = null;

// ─── Init ───────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadBusinesses();
  document.getElementById('btn-add-business').addEventListener('click', openAddModal);
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('btn-cancel').addEventListener('click', closeModal);
  document.getElementById('btn-back-thread').addEventListener('click', closeThread);
  document.getElementById('btn-delete-thread').addEventListener('click', deleteActiveThread);
  document.getElementById('business-form').addEventListener('submit', saveBusinessForm);
  document.getElementById('modal-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
  });

  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('oauth_success') === 'true') {
    alert("🎉 SUCCESS! Your GHL Access Token and Refresh Token have been generated and securely saved to your database.");
    // Clear the parameter from the URL bar
    window.history.replaceState({}, document.title, "/");
  }
});

// ─── Businesses ───────────────────────────────────
async function loadBusinesses() {
  const res = await fetch(`${API}/api/businesses`);
  const data = await res.json();
  const list = document.getElementById('business-list');
  const businesses = data.businesses || [];

  if (!businesses.length) {
    list.innerHTML = '<div class="loading-state">No businesses yet</div>';
    return;
  }

  list.innerHTML = businesses.map(b => `
    <div class="business-item ${activeBusiness?.id === b.id ? 'active' : ''}"
         onclick="selectBusiness(${JSON.stringify(b).replace(/"/g, '&quot;')})"
         data-id="${b.id}">
      <div class="biz-dot"></div>
      <div class="biz-name">${b.name}</div>
    </div>
  `).join('');
}

async function selectBusiness(business) {
  activeBusiness = business;
  document.getElementById('page-title').textContent = business.name;
  document.getElementById('stats-row').style.display = 'grid';

  // Mark active in sidebar
  document.querySelectorAll('.business-item').forEach(el => el.classList.remove('active'));
  const el = document.querySelector(`.business-item[data-id="${business.id}"]`);
  if (el) el.classList.add('active');

  // Load stats + conversations in parallel
  await Promise.all([loadStats(business.id), loadConversations(business.id)]);

  // Show edit + webhook info button
  document.getElementById('topbar-actions').innerHTML = `
    <button class="btn-icon" onclick="openCampaignsModal('${business.id}')">🎯 Campaigns</button>
    <button class="btn-icon" onclick="openEditModal('${business.id}')">⚙ Master Settings</button>
    <button class="btn-icon" onclick="showWebhookInfo('${business.id}')">🔗 Default Webhook</button>
  `;
}

async function loadStats(businessId) {
  try {
    const res = await fetch(`${API}/api/businesses/${businessId}/stats`);
    const s = await res.json();
    document.getElementById('stat-convos').textContent = s.total_conversations ?? '—';
    document.getElementById('stat-messages').textContent = s.total_messages ?? '—';
    document.getElementById('stat-ai').textContent = s.ai_replies_sent ?? '—';
  } catch(e) {
    console.error('Stats error:', e);
  }
}

async function loadConversations(businessId) {
  const area = document.getElementById('content-area');
  area.innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div><div class="empty-title">Loading conversations...</div></div>';
  try {
    const res = await fetch(`${API}/api/conversations?business_id=${businessId}`);
    const data = await res.json();
    const convs = data.conversations || [];

    if (!convs.length) {
      area.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">💬</div>
          <div class="empty-title">No conversations yet</div>
          <div class="empty-sub">Set up the GHL webhook and conversations will appear here automatically</div>
        </div>`;
      return;
    }

    area.innerHTML = `<div class="conv-grid">${convs.map(c => convCard(c)).join('')}</div>`;
  } catch(e) {
    area.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Failed to load</div><div class="empty-sub">Check your API connection</div></div>';
  }
}

function convCard(c) {
  const contact = c.contacts || {};
  const name = contact.name || c.ghl_contact_id.slice(0,8) + '...';
  const phone = contact.phone || '';
  const initial = name.charAt(0).toUpperCase();
  const date = c.last_message_at ? new Date(c.last_message_at).toLocaleDateString('en-US', {month:'short', day:'numeric'}) : '—';

  return `
    <div class="conv-card" onclick="openThread('${c.id}', '${name}')">
      <div class="conv-avatar">${initial}</div>
      <div class="conv-info">
        <div class="conv-name">${name}</div>
        <div class="conv-preview">${phone || 'No phone'}</div>
      </div>
      <div class="conv-meta">
        <div class="conv-time">${date}</div>
        <span class="conv-badge">${c.total_messages} msgs</span>
      </div>
    </div>`;
}

// ─── Thread ───────────────────────────────────
async function openThread(conversationId, contactName) {
  activeThreadId = conversationId;
  document.getElementById('thread-contact-name').textContent = contactName;
  document.getElementById('thread-messages').innerHTML = '<div style="color:var(--text-3);text-align:center;padding:40px">Loading...</div>';
  document.getElementById('thread-panel').classList.add('open');

  const res = await fetch(`${API}/api/conversations/${conversationId}/messages`);
  const data = await res.json();
  const msgs = data.messages || [];
  const container = document.getElementById('thread-messages');

  if (!msgs.length) {
    container.innerHTML = '<div style="color:var(--text-3);text-align:center;padding:40px">No messages yet</div>';
    return;
  }

  container.innerHTML = msgs.map(m => `
    <div class="msg-bubble ${m.role}">
      <div class="msg-body">${escapeHtml(m.content)}</div>
      <div class="msg-time">${m.role === 'user' ? '👤 Contact' : '🤖 AI'} · ${formatTime(m.created_at)}</div>
    </div>
  `).join('');
  container.scrollTop = container.scrollHeight;
}

function closeThread() {
  activeThreadId = null;
  document.getElementById('thread-panel').classList.remove('open');
}

async function deleteActiveThread() {
  if (!activeThreadId) return;
  if (!confirm("Are you sure you want to permanently delete this conversation and all its messages?")) return;
  
  try {
    const res = await fetch(`${API}/api/conversations/${activeThreadId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    
    closeThread();
    if (activeBusiness) {
      await loadConversations(activeBusiness.id);
      await loadStats(activeBusiness.id);
    }
  } catch(e) {
    alert("Failed to delete conversation: " + e.message);
  }
}

// ─── Modal ───────────────────────────────────
function openAddModal() {
  document.getElementById('modal-title').textContent = 'Add Business';
  document.getElementById('form-business-id').value = '';
  document.getElementById('business-form').reset();
  document.getElementById('btn-delete-business').style.display = 'none';
  document.getElementById('modal-overlay').classList.add('open');
}

async function openEditModal(businessId) {
  document.getElementById('modal-title').textContent = 'Edit Business Settings';
  const res = await fetch(`${API}/api/businesses/${businessId}`);
  const data = await res.json();
  const b = data.business;

  document.getElementById('form-business-id').value = b.id;
  document.getElementById('form-name').value = b.name || '';
  document.getElementById('form-location-id').value = b.ghl_location_id || '';
  document.getElementById('form-api-key').value = ''; // don't pre-fill masked key
  document.getElementById('form-client-id').value = b.ghl_client_id || '';
  document.getElementById('form-client-secret').value = ''; // don't pre-fill
  document.getElementById('form-access-token').value = ''; // don't pre-fill
  document.getElementById('form-refresh-token').value = ''; // don't pre-fill
  document.getElementById('form-calendar-id').value = b.ghl_calendar_id || '';
  document.getElementById('aiPrompt').value = b.ai_prompt || '';
  document.getElementById('pricingInfo').value = b.pricing_info || '';
  document.getElementById('outreachMessage').value = b.outreach_message || '';
  document.getElementById('form-website').value = b.website_url || '';
  document.getElementById('form-calendar').value = b.calendar_link || '';
  document.getElementById('form-delay-min').value = b.delay_min ?? 60;
  document.getElementById('form-delay-max').value = b.delay_max ?? 180;
  document.getElementById('form-model').value = b.ai_model || 'gemini-2.5-pro';
  document.getElementById('btn-delete-business').style.display = 'block';
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
}

async function saveBusinessForm(e) {
  e.preventDefault();
  const businessId = document.getElementById('form-business-id').value;
  const btn = document.getElementById('btn-save');
  btn.textContent = 'Saving...'; btn.disabled = true;

  const payload = {
    name: document.getElementById('form-name').value,
    ghl_location_id: document.getElementById('form-location-id').value,
    ghl_api_key: document.getElementById('form-api-key').value,
    ghl_client_id: document.getElementById('form-client-id').value || null,
    ghl_client_secret: document.getElementById('form-client-secret').value || null,
    ghl_access_token: document.getElementById('form-access-token').value || null,
    ghl_refresh_token: document.getElementById('form-refresh-token').value || null,
    ghl_calendar_id: document.getElementById('form-calendar-id').value || null,
    ai_prompt: document.getElementById('aiPrompt').value,
    pricing_info: document.getElementById('pricingInfo').value || null,
    outreach_message: document.getElementById('outreachMessage').value || null,
    website_url: document.getElementById('form-website').value || null,
    calendar_link: document.getElementById('form-calendar').value || null,
    delay_min: parseInt(document.getElementById('form-delay-min').value),
    delay_max: parseInt(document.getElementById('form-delay-max').value),
    ai_model: document.getElementById('form-model').value,
  };

  // Remove empty keys on edit (don't overwrite with blank)
  if (businessId) {
    if (!payload.ghl_api_key) delete payload.ghl_api_key;
    if (!payload.ghl_client_secret) delete payload.ghl_client_secret;
    if (!payload.ghl_access_token) delete payload.ghl_access_token;
    if (!payload.ghl_refresh_token) delete payload.ghl_refresh_token;
  }

  try {
    const method = businessId ? 'PUT' : 'POST';
    const url = businessId ? `${API}/api/businesses/${businessId}` : `${API}/api/businesses`;
    const res = await fetch(url, {
      method, headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(await res.text());
    closeModal();
    await loadBusinesses();
    if (activeBusiness) selectBusiness({...activeBusiness, ...payload});
  } catch(err) {
    alert('Error saving: ' + err.message);
  } finally {
    btn.textContent = 'Save Business'; btn.disabled = false;
  }
}

async function deleteActiveBusiness() {
  const businessId = document.getElementById('form-business-id').value;
  if (!businessId) return;
  if (!confirm("🚨 WARNING: Are you sure you want to completely delete this Business? This will permanently erase ALL conversations, messages, and campaigns attached to it!")) return;
  
  try {
    const res = await fetch(`${API}/api/businesses/${businessId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    
    closeModal();
    activeBusiness = null;
    document.getElementById('topbar-actions').innerHTML = '';
    document.getElementById('page-title').textContent = 'Select a Business';
    document.getElementById('stats-row').style.display = 'none';
    document.getElementById('content-area').innerHTML = '<div class="empty-state"><div class="empty-icon">💬</div><div class="empty-title">Business deleted successfully</div></div>';
    await loadBusinesses();
  } catch(e) {
    alert("Failed to delete business: " + e.message);
  }
}

// ─── Webhook Info ───────────────────────────────────
function showWebhookInfo(businessId) {
  const host = window.location.origin;
  const webhookUrl = `${host}/webhook/inbound`;
  alert(`DEFAULT GHL Webhook URL:\n\n${webhookUrl}\n\nPaste this into your Default GHL Workflow > Webhook action.\n\nRequired fields to send:\n• location_id: {{location.id}}\n• contact_id: {{contact.id}}\n• message: {{message.body}}\n• name: {{contact.fullNameLowerCase}}\n• phone: {{contact.phone}}`);
}

function copyCampaignWebhook(campaignId) {
  const host = window.location.origin;
  const webhookUrl = `${host}/webhook/inbound?campaign_id=${campaignId}`;
  navigator.clipboard.writeText(webhookUrl).then(() => alert('Copied Campaign Webhook URL to clipboard!'));
}

// ─── Campaigns Logic ───────────────────────────────────
let campaignsListCache = [];

async function openCampaignsModal(businessId) {
  document.getElementById('campaigns-modal-title').textContent = `Campaigns for ${activeBusiness.name}`;
  document.getElementById('campaigns-list-modal').classList.add('open');
  await loadCampaignsList();
}

async function loadCampaignsList() {
  const container = document.getElementById('campaigns-list-container');
  container.innerHTML = 'Loading campaigns...';
  try {
    const res = await fetch(`${API}/api/campaigns?business_id=${activeBusiness.id}`);
    const camps = await res.json();
    campaignsListCache = camps; // Store globally for reference
    
    if (!camps.length) {
      container.innerHTML = '<div style="color:var(--text-3);padding:20px;">No campaigns created yet. Click + New Campaign to start!</div>';
      return;
    }
    container.innerHTML = camps.map((c, index) => `
      <div style="background:#1a2235; padding:15px; border-radius:8px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <strong style="color:white; display:block;">${c.name}</strong>
          <small style="color:var(--text-3);">ID: ${c.id.substring(0,8)}...</small>
        </div>
        <div style="display:flex; gap:10px;">
          <button class="btn-secondary" style="padding:6px 12px;" onclick="copyCampaignWebhook('${c.id}')">🔗 Copy Webhook</button>
          <button class="btn-secondary" style="padding:6px 12px;" onclick="openCampaignEditModalCache(${index})">Edit</button>
          <button class="btn-secondary" style="padding:6px 12px; background:var(--brand-red); border-color:var(--brand-red);" onclick="deleteCampaign('${c.id}')">Delete</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = '<div style="color:var(--brand-red)">Failed to load campaigns</div>';
  }
}

function openCampaignEditModalCache(index) {
    const campaign = campaignsListCache[index];
    openCampaignEditModal(campaign);
}

function openCampaignEditModal(campaign = null) {
  document.getElementById('campaign-form').reset();
  if (campaign) {
    document.getElementById('campaign-edit-modal-title').textContent = 'Edit Campaign';
    document.getElementById('form-campaign-id').value = campaign.id;
    document.getElementById('campName').value = campaign.name || '';
    document.getElementById('campAiPrompt').value = campaign.ai_prompt || '';
    document.getElementById('campPricingInfo').value = campaign.pricing_info || '';
    document.getElementById('campOutreachMessage').value = campaign.outreach_message || '';
    document.getElementById('campGhlCalendarId').value = campaign.ghl_calendar_id || '';
    document.getElementById('campCalendarLink').value = campaign.calendar_link || '';
  } else {
    document.getElementById('campaign-edit-modal-title').textContent = 'New Campaign';
    document.getElementById('form-campaign-id').value = '';
    // Pre-fill prompt from default business
    document.getElementById('campAiPrompt').value = activeBusiness.ai_prompt || '';
  }
  document.getElementById('campaign-edit-modal').classList.add('open');
}

document.getElementById('campaign-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const campaignId = document.getElementById('form-campaign-id').value;
  const btn = document.getElementById('btn-save-campaign');
  btn.textContent = 'Saving...'; btn.disabled = true;

  const payload = {
    name: document.getElementById('campName').value,
    ai_prompt: document.getElementById('campAiPrompt').value,
    pricing_info: document.getElementById('campPricingInfo').value || null,
    outreach_message: document.getElementById('campOutreachMessage').value || null,
    ghl_calendar_id: document.getElementById('campGhlCalendarId').value || null,
    calendar_link: document.getElementById('campCalendarLink').value || null,
  };

  try {
    let url = `${API}/api/campaigns`;
    let method = 'POST';
    if (campaignId) {
      url = `${API}/api/campaigns/${campaignId}`;
      method = 'PUT';
    } else {
      payload.business_id = activeBusiness.id;
    }

    const res = await fetch(url, {
      method, headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(await res.text());
    
    document.getElementById('campaign-edit-modal').classList.remove('open');
    await loadCampaignsList();
  } catch(err) {
    alert('Error saving campaign: ' + err.message);
  } finally {
    btn.textContent = 'Save Campaign'; btn.disabled = false;
  }
});

async function deleteCampaign(campaignId) {
  if (!confirm("Are you sure you want to delete this campaign?")) return;
  try {
    const res = await fetch(`${API}/api/campaigns/${campaignId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    await loadCampaignsList();
  } catch(e) {
    alert("Failed to delete campaign: " + e.message);
  }
}


// ─── Helpers ───────────────────────────────────
function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
}

function formatTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('en-US', {month:'short', day:'numeric', hour:'numeric', minute:'2-digit'});
}
