"""Shared agent infrastructure: sales agent, analyst, permissions, approvals, isolation, WhatsApp."""
import hashlib
import hmac
import json
import uuid

from app.agents import runtime  # noqa: F401  (registers tools)
from app.agents.registry import AgentContext, TOOLS, ToolDenied, check_permission
from app.agents.runtime_exec import execute
from app.core.tenant_context import tenant_scope
from app.database.models import Gym, User
from app.database.session import SessionLocal
from tests.conftest import API, create_member, fill_profile, publish_site, register_gym, set_plan


def _chat(client, owner, message, conversation_id=None):
    resp = client.post(f"{API}/ai/sales-agent/test", headers=owner,
                       json={"message": message, "conversation_id": conversation_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_sales_agent_answers_only_from_approved_data_and_books_trial(client, owner):
    fill_profile(client, owner)
    r = _chat(client, owner, "Hi, what are your membership fees?")
    assert r["engine"] == "rules" and r["agent"] == "lead_conversion"
    plans = client.get(f"{API}/membership-plans", headers=owner).json()
    assert all(f"{p['price']:,.0f}" in r["reply"] for p in plans)
    conv = r["conversation_id"]
    r = _chat(client, owner, "Is parking available at the gym?", conv)
    assert "two-wheeler parking" in r["reply"]  # approved FAQ answer
    r = _chat(client, owner, "I want a free trial. My name is Priya Desai, 98989 12345", conv)
    lead = client.get(f"{API}/crm/leads", headers=owner).json()["items"][0]
    assert lead["name"] == "Priya Desai" and lead["phone"] == "9898912345" and lead["source"] == "website_chat"
    assert "1." in r["reply"] and "Reply 1, 2 or 3" in r["reply"]
    r = _chat(client, owner, "1", conv)
    assert "booked" in r["reply"].lower()
    lead = client.get(f"{API}/crm/leads/{lead['id']}", headers=owner).json()
    assert lead["lead"]["status"] == "trial_booked" and lead["trials"][0]["status"] == "booked"
    assert lead["lead"]["first_response_at"]  # the AI reply counts as a response


def test_unknown_question_escalates_and_human_takeover_silences_ai(client, owner):
    fill_profile(client, owner)
    r = _chat(client, owner, "Do you offer a refund if I get injured?")
    assert "team" in r["reply"].lower()
    conv = client.get(f"{API}/ai/conversations/{r['conversation_id']}", headers=owner).json()
    assert conv["status"] == "human" and conv["escalation_reason"]
    tasks = client.get(f"{API}/crm/tasks", headers=owner, params={"kind": "escalation"}).json()["items"]
    assert len(tasks) == 1
    r2 = _chat(client, owner, "Hello?", r["conversation_id"])
    assert r2["status"] == "human" and r2["reply"] is None
    client.post(f"{API}/ai/conversations/{r['conversation_id']}/handback", headers=owner)
    assert _chat(client, owner, "What are your timings?", r["conversation_id"])["reply"]


def test_public_website_chat(client, owner):
    fill_profile(client, owner)
    site = publish_site(client, owner)
    sid = uuid.uuid4().hex
    resp = client.post(f"{API}/public/sites/{site['slug']}/chat", json={
        "session_id": sid, "message": "My name is Karan, call me back on 9811122233", "utm_source": "chatgpt.com"})
    assert resp.status_code == 200 and resp.json()["reply"]
    lead = client.get(f"{API}/crm/leads", headers=owner).json()["items"][0]
    assert lead["phone"] == "9811122233" and lead["source"] == "ai_search" and lead["attribution"]["method"] == "utm"


def test_analyst_numbers_come_from_the_database(client, owner):
    member = create_member(client, owner)
    client.post(f"{API}/payments", headers=owner, json={"member_id": member["id"], "amount": 2500, "paid": False})
    r = client.post(f"{API}/ai/assistant", headers=owner, json={"message": "How much money is outstanding?"}).json()
    assert r["agent"] == "recovery" and "₹2,500" in r["reply"]
    assert any(e["tool"] == "revenue_summary" and e["result"]["outstanding"] == 2500 for e in r["evidence"])
    runs = client.get(f"{API}/ai/usage", headers=owner).json()
    assert runs["by_agent"]["recovery"]["runs"] == 1 and runs["engine"] == "rules"


def test_tool_permissions(client, owner):
    trainer = client.post(f"{API}/users", headers=owner, json={"full_name": "T", "email": "t@gym.example.com",
                                                                "password": "trainerpass", "role": "trainer"})
    assert trainer.status_code == 201
    tok = client.post(f"{API}/auth/login", json={"email": "t@gym.example.com", "password": "trainerpass"}).json()
    t_headers = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.post(f"{API}/ai/assistant", headers=t_headers, json={"message": "revenue?"}).status_code == 403
    with SessionLocal() as db:
        gym = db.query(Gym).first()
        with tenant_scope(gym.id):
            public_ctx = AgentContext(db=db, agent_key="lead_conversion")
            try:
                check_permission(public_ctx, TOOLS["list_leads"])
                raise AssertionError("public visitor reached a staff tool")
            except ToolDenied:
                pass
            # A visitor cannot use a staff-only tool even by naming it
            assert execute(public_ctx, "revenue_summary", {"days": 30})["denied"] is True


def test_consequential_actions_need_confirmation_and_are_tenant_scoped(client, owner):
    lead = client.post(f"{API}/crm/leads", headers=owner, json={"name": "Asha", "phone": "9123412345"}).json()
    with SessionLocal() as db:
        owner_user = db.query(User).filter(User.role == "gym_owner").first()
        with tenant_scope(owner_user.gym_id):
            ctx = AgentContext(db=db, agent_key="business_analyst", user=owner_user)
            out = execute(ctx, "send_message_to_lead", {"lead_id": lead["id"], "message": "Hi Asha!"})
    assert out["status"] == "pending_confirmation"
    actions = client.get(f"{API}/ai/actions", headers=owner).json()
    assert len(actions) == 1 and actions[0]["tool"] == "send_message_to_lead"
    other, _ = register_gym(client, name="Other Gym", email="other3@gym.example.com")
    assert client.post(f"{API}/ai/actions/{actions[0]['id']}/confirm", headers=other).status_code == 404
    done = client.post(f"{API}/ai/actions/{actions[0]['id']}/confirm", headers=owner).json()
    assert done["status"] == "executed"
    assert done["result"]["status"] == "drafted"  # no WhatsApp opt-in -> staff draft instead of sending
    assert client.post(f"{API}/ai/actions/{actions[0]['id']}/confirm", headers=owner).status_code == 409


def test_agent_tools_cannot_see_other_gyms(client, owner):
    client.post(f"{API}/crm/leads", headers=owner, json={"name": "Gym A lead", "phone": "9123400099"})
    other, other_user = register_gym(client, name="Other Gym", email="other4@gym.example.com")
    with SessionLocal() as db:
        user = db.get(User, uuid.UUID(other_user["id"]))
        with tenant_scope(user.gym_id):
            out = execute(AgentContext(db=db, agent_key="crm_follow_up", user=user), "list_leads", {})
    assert out["total"] == 0


def test_plan_gates_agents(client, owner):
    set_plan(client, owner, "starter")
    assert client.post(f"{API}/ai/assistant", headers=owner, json={"message": "How is my gym doing?"}).status_code == 402
    assert client.post(f"{API}/ai/sales-agent/test", headers=owner, json={"message": "hi"}).status_code == 402


def _wa(client, body):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(b"wa_app_secret", raw, hashlib.sha256).hexdigest()
    return client.post(f"{API}/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})


def _wa_message(msg_id, sender, text, phone_number_id="1234567890"):
    return {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": phone_number_id}, "contacts": [{"wa_id": sender, "profile": {"name": "Ravi"}}],
        "messages": [{"id": msg_id, "from": sender, "type": "text", "text": {"body": text}}]}}]}]}


def test_whatsapp_webhook(client, owner):
    fill_profile(client, owner)
    assert client.get(f"{API}/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wa_verify",
                                                          "hub.challenge": "42"}).text == "42"
    assert client.post(f"{API}/webhooks/whatsapp", content=b"{}", headers={"X-Hub-Signature-256": "sha256=bad"}
                       ).status_code == 401
    # Unmapped number: ignored
    assert _wa(client, _wa_message("wamid.1", "919800000001", "hi")).json()["handled"] == 0
    assert client.put(f"{API}/integrations/whatsapp", headers=owner,
                      json={"phone_number_id": "1234567890"}).status_code == 200
    assert _wa(client, _wa_message("wamid.2", "919800000001", "What are your fees?")).json()["handled"] == 1
    assert _wa(client, _wa_message("wamid.2", "919800000001", "What are your fees?")).json()["handled"] == 0  # dedup
    lead = client.get(f"{API}/crm/leads", headers=owner).json()["items"][0]
    assert lead["source"] == "whatsapp" and lead["whatsapp_opt_in"] is True and lead["name"] == "Ravi"
    convs = client.get(f"{API}/ai/conversations", headers=owner, params={"channel": "whatsapp"}).json()
    msgs = client.get(f"{API}/ai/conversations/{convs[0]['id']}", headers=owner).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    _wa(client, _wa_message("wamid.3", "919800000001", "STOP"))
    assert client.get(f"{API}/crm/leads/{lead['id']}", headers=owner).json()["lead"]["opted_out"] is True
    # Opted-out leads are never messaged by workflows
    with SessionLocal() as db:
        from app.database.models import Lead
        from app.services.messaging import send_to_lead

        lead_row = db.get(Lead, uuid.UUID(lead["id"]))
        with tenant_scope(lead_row.gym_id):
            assert send_to_lead(db, lead_row, "Offer!", category="sales_follow_up").status == "blocked"


def test_claude_tool_loop_with_mocked_api(client, owner, monkeypatch):
    """The real tool-use loop: model calls a tool, gets the DB result back, then answers. Usage is costed."""
    from types import SimpleNamespace as NS

    from app.integrations.ai import claude

    member = create_member(client, owner)
    client.post(f"{API}/payments", headers=owner, json={"member_id": member["id"], "amount": 1200, "paid": False})
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        usage = NS(input_tokens=1000, output_tokens=200)
        if len(calls) == 1:
            assert any(t["name"] == "revenue_summary" for t in kwargs["tools"])
            assert all(t["input_schema"]["additionalProperties"] is False for t in kwargs["tools"])
            return NS(stop_reason="tool_use", usage=usage, content=[
                NS(type="tool_use", id="tu_1", name="revenue_summary", input={"days": 30})])
        result = json.loads(kwargs["messages"][-1]["content"][0]["content"])
        return NS(stop_reason="end_turn", usage=usage, content=[
            NS(type="text", text=f"Outstanding is ₹{result['outstanding']:,.0f}.")])

    monkeypatch.setattr(claude, "is_configured", lambda: True)
    monkeypatch.setattr(claude, "create", fake_create)
    r = client.post(f"{API}/ai/assistant", headers=owner, json={"message": "What is outstanding?"}).json()
    assert r["engine"] == "claude" and r["reply"] == "Outstanding is ₹1,200."
    assert [t["name"] for t in r["tools_called"]] == ["revenue_summary"]
    usage = client.get(f"{API}/ai/usage", headers=owner).json()["by_agent"]["recovery"]
    assert usage["input_tokens"] == 2000 and usage["output_tokens"] == 400
    assert usage["cost_usd"] == round((2000 * 4 + 400 * 20) / 1_000_000, 6)
