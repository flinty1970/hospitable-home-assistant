/* Admin-only panel. No credentials or property/guest data are bundled or cached. */
class HospitableStaysPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;padding:24px;max-width:900px;font:16px var(--paper-font-body1_-_font-family,Arial);color:var(--primary-text-color)}
      section{border:1px solid var(--divider-color,#ccc);border-radius:12px;padding:20px;margin:20px 0}
      button{padding:10px 16px;margin:8px 8px 8px 0;cursor:pointer;border-radius:8px;border:1px solid var(--divider-color,#aaa);background:var(--card-background-color,white);color:var(--primary-text-color)}
      input{box-sizing:border-box;width:100%;padding:12px;font:inherit;background:var(--card-background-color,white);color:var(--primary-text-color);border:1px solid var(--divider-color,#aaa);border-radius:8px}
      p,li{line-height:1.5}.muted{color:var(--secondary-text-color)}
    </style><h1>Hospitable Stays</h1><p>Webhook status</p><button id="refresh">Refresh status</button><p id="notice" role="status"></p><main></main>`;
    this.shadowRoot.querySelector("#refresh").onclick = () => this.refresh();
  }
  set hass(value) {
    this._hass = value;
    if (!this._loaded) { this._loaded = true; this.refresh(); }
  }
  async refresh() {
    const main = this.shadowRoot.querySelector("main");
    main.replaceChildren();
    try {
      const rows = await this._hass.callWS({ type: "hospitable_stays/status" });
      if (!rows.length) this.notice("No loaded Hospitable Stays integrations.");
      else this.notice("");
      for (const row of rows) this.renderEntry(main, row);
    } catch (_) { this.notice("Unable to load status. Administrator access is required."); }
  }
  notice(text) { this.shadowRoot.querySelector("#notice").textContent = text; }
  renderEntry(main, row) {
    const card = document.createElement("section");
    const heading = document.createElement("h2");
    heading.textContent = row.title; card.append(heading);
    const addText = (text) => { const p = document.createElement("p"); p.textContent = text; card.append(p); };
    if (!row.cloud_active) {
      addText(`Push updates need Home Assistant Cloud (Nabu Casa). The integration is working in polling mode, with updates every ${row.minutes} minutes.`);
      main.append(card); return;
    }
    addText(`Last webhook: ${row.last_received || "Never"} · ${row.last_event || "None"}`);
    addText(`Polling fallback: ${row.fallback ? "Active" : "Standby"}. Polling continues every ${row.minutes} minutes.`);
    addText(`Last successful poll: ${row.last_poll || "Never"}`);
    if (!row.url) {
      addText("Open Settings → Devices & services → Hospitable Stays → Configure → Webhooks → Enable push updates.");
      main.append(card); return;
    }
    const label = document.createElement("label"); label.textContent = "Private Nabu Casa webhook URL";
    const input = document.createElement("input"); input.readOnly = true; input.value = row.url; label.append(input); card.append(label);
    const copy = document.createElement("button"); copy.textContent = "Copy URL";
    copy.onclick = async () => {
      try {
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(row.url);
        else { input.focus(); input.select(); if (!document.execCommand("copy")) throw new Error(); }
        this.notice("Webhook URL copied.");
      } catch (_) { input.focus(); input.select(); this.notice("Select the URL and use your browser's Copy action."); }
    };
    card.append(copy);
    const test = document.createElement("button"); test.textContent = "Send test event";
    test.onclick = async () => {
      test.disabled = true;
      try {
        const result = await this._hass.callWS({ type: "hospitable_stays/test", entry_id: row.entry_id });
        this.notice(result.processed ? "Signed local sample processed. Use Test in Hospitable to verify cloud delivery." : "Local test failed. Check Cloud connection and webhook configuration.");
      } catch (_) { this.notice("Local test failed. Check administrator access and Cloud connection."); }
      finally { test.disabled = false; }
    };
    card.append(test);
    const steps = document.createElement("ol");
    for (const text of ["Copy the private webhook URL.", "In Hospitable open Apps → Webhooks under Tools → Webhooks tab → + Add new.", "Give it a name, paste the URL, select Reservations, then Save.", "Click Test in Hospitable and refresh this screen."]) {
      const li = document.createElement("li"); li.textContent = text; steps.append(li);
    }
    card.append(steps);
    addText("Anyone with the URL can post to it, which is why signature verification matters. Keep it private. Times above are UTC. The local test does not verify cloud routing.");
    main.append(card);
  }
}
if (!customElements.get("hospitable-stays-panel")) customElements.define("hospitable-stays-panel", HospitableStaysPanel);
