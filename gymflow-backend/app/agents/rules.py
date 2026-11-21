"""Deterministic engines, used when no AI provider is configured (and labelled engine="rules").

Sales: a small state machine that only ever answers from approved information and tool results.
Analyst: maps the question to tools and formats the numbers they return.
"""
import re
from datetime import datetime

from app.agents.registry import AgentContext
from app.agents.runtime_exec import execute

PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})")
NAME_RE = re.compile(r"\b(?:my name is|i am|i'm|this is|name[:\-]?)\s+([A-Za-z][A-Za-z .']{1,40})", re.I)
ESCALATE_WORDS = ("refund", "complain", "complaint", "injur", "pain", "doctor", "medical", "pregnan", "manager",
                  "human", "real person", "speak to someone", "call me", "legal", "angry", "fraud")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", text.lower()))


def _has(text: str, *keys: str) -> bool:
    t = text.lower()
    return any(k in t for k in keys)


# ================================================================ sales

def sales_reply(ctx: AgentContext, message: str) -> str:
    conv = ctx.conversation
    state = dict(conv.state or {})
    text = message.strip()
    info = execute(ctx, "get_gym_info", {})
    gym = info.get("gym", "the gym")

    # capture details whenever they appear
    phone = PHONE_RE.search(text)
    name = NAME_RE.search(text)
    if state.get("awaiting") == "name" and not name and len(text.split()) <= 4 and not phone and text.isascii():
        name_value = text.strip(" .").title()
    else:
        name_value = name.group(1).strip(" .").title() if name else None
    details = {}
    if phone:
        details["phone"] = re.sub(r"\D", "", phone.group(1))
    if name_value:
        details["name"] = name_value
    if _has(text, "trial", "visit", "try ", "demo", "free session"):
        details["wants_trial"] = True
        state["wants_trial"] = True
    for interest in ("weight loss", "fat loss", "strength", "muscle", "yoga", "zumba", "cardio", "crossfit",
                     "personal training", "general fitness"):
        if interest in text.lower():
            details["fitness_interest"] = interest
    if details or (ctx.channel == "whatsapp" and not conv.lead_id):
        saved = execute(ctx, "save_lead_details", details)
        if saved.get("saved"):
            state["lead_saved"] = True

    if any(w in text.lower() for w in ESCALATE_WORDS):
        execute(ctx, "escalate_to_staff", {"reason": f"Visitor asked: {text[:150]}", "stop_ai": True})
        conv.state = state
        return ("I'll connect you with our team - a staff member will reply here shortly. "
                + (f"You can also call {info['phone']}." if info.get("phone") else ""))

    # slot choice
    if state.get("awaiting") == "slot" and state.get("slots"):
        choice = re.search(r"\b([1-3])\b", text)
        if choice:
            slot = state["slots"][int(choice.group(1)) - 1]
            booked = execute(ctx, "book_trial", {"starts_at": slot["starts_at"]})
            state.pop("awaiting", None)
            conv.state = state
            if booked.get("booked"):
                return f"Done! Your trial is booked for {booked['when']}. See you at {gym}. 💪"
            return f"Sorry, that slot couldn't be booked ({booked.get('error')}). Shall I show other times?"

    replies: list[str] = []
    faq = _match_faq(text, info.get("faqs") or [])
    if faq:  # an owner-approved answer always wins over generic facts
        replies.append(faq["a"])
    if _has(text, "price", "fee", "cost", "plan", "membership", "charges", "rate"):
        plans = execute(ctx, "list_membership_plans", {})
        if plans.get("plans"):
            lines = [f"• {p['name']}: {plans['currency']} {p['price']:,.0f}" for p in plans["plans"]]
            replies.append("Our membership plans:\n" + "\n".join(lines))
    if _has(text, "time", "timing", "hours", "open", "close", "morning", "evening"):
        if info.get("hours"):
            replies.append("Timings: " + "; ".join(f"{h['days']} {h['opens']}–{h['closes']}" for h in info["hours"]))
    if _has(text, "where", "address", "location", "located", "direction"):
        if info.get("address"):
            replies.append(f"We're at {info['address']}.")
    if not faq and _has(text, "facilit", "equipment", "machine", "amenit", "parking", "shower", "locker"):
        if info.get("facilities"):
            replies.append("Facilities: " + ", ".join(info["facilities"]) + ".")
    if _has(text, "trainer", "coach", "personal training", "pt "):
        if info.get("trainers"):
            replies.append("Our coaches: " + ", ".join(
                f"{t['name']}" + (f" ({t['specialization']})" if t.get("specialization") else "")
                for t in info["trainers"][:5]) + ".")

    if state.get("wants_trial"):
        if not conv.lead_id or not state.get("lead_saved"):
            state["awaiting"] = "name" if not name_value else "phone"
            replies.append("I'd be happy to book a free trial. " +
                           ("What's your name and phone number?" if not phone else "May I have your name?"))
        else:
            slots = execute(ctx, "find_trial_slots", {"days": 4}).get("slots", [])[:3]
            if slots:
                state["slots"], state["awaiting"] = slots, "slot"
                replies.append("Here are the next available trial slots:\n" + "\n".join(
                    f"{i + 1}. {s['local']}" for i, s in enumerate(slots)) + "\nReply 1, 2 or 3 to book.")
            else:
                execute(ctx, "escalate_to_staff", {"reason": "Wants a trial but no slots are free", "stop_ai": False})
                replies.append("All trial slots are full right now - our team will message you with a time.")
    elif not replies:
        if _has(text, "hi", "hello", "hey", "namaste", "kem cho") and len(text) < 30:
            replies.append(f"Hi! Welcome to {gym}. I can help with plans and fees, timings, location, or booking a "
                           "free trial. What would you like to know?")
        else:
            execute(ctx, "escalate_to_staff", {"reason": f"Question not covered: {text[:150]}", "stop_ai": False})
            replies.append("I don't have that information, so I've asked our team to get back to you. "
                           "Meanwhile, I can share plans, timings or book a free trial.")
    if not conv.lead_id and not state.get("asked_contact") and not state.get("wants_trial") and ctx.channel != "whatsapp":
        state["asked_contact"] = True
        replies.append("If you'd like a call back, share your name and phone number.")
    conv.state = state
    return "\n\n".join(replies)


def _match_faq(text: str, faqs: list[dict]) -> dict | None:
    words = _words(text)
    best, best_score = None, 0
    for f in faqs:
        overlap = len(words & _words(f["q"]))
        if overlap > best_score:
            best, best_score = f, overlap
    return best if best_score >= 2 else None


# ================================================================ analyst

def _fmt_money(v, cur="₹") -> str:
    return f"{cur}{float(v or 0):,.0f}"


def analyst_reply(ctx: AgentContext, question: str) -> str:
    q = question.lower()
    sections: list[str] = []

    if _has(q, "seven-day", "7-day", "7 day", "seven day", "week plan", "growth plan"):
        recs = execute(ctx, "recommendations", {}).get("recommendations", [])
        acts = execute(ctx, "todays_actions", {}).get("actions", [])
        plan = [f"**Day {i + 1}:** {a['title']} → {a['href']}" for i, a in enumerate(acts[:4])]
        plan += [f"**Day {len(plan) + i + 1}:** {r['title']} → {r['href']}" for i, r in enumerate(recs[: 7 - len(plan)])]
        return "Here's a 7-day plan based on your current data:\n\n" + "\n".join(plan[:7]) if plan else \
            "Nothing urgent stands out in your data right now."
    if _has(q, "today", "what should i do", "priorit", "increase membership", "top five", "top 5", "opportunit"):
        acts = execute(ctx, "todays_actions", {}).get("actions", [])
        recs = execute(ctx, "recommendations", {}).get("recommendations", [])
        if acts:
            sections.append("**Today's actions**\n" + "\n".join(f"- {a['title']} ({a['detail']}) → {a['href']}" for a in acts))
        if recs:
            sections.append("**Top opportunities**\n" + "\n".join(
                f"- {r['title']}: " + ", ".join(f"{e['label']} {e['value']}" for e in r["evidence"]) + f" → {r['href']}"
                for r in recs[:5]))
    if _has(q, "outstanding", "owed", "pending payment", "dues", "unpaid", "money"):
        r = execute(ctx, "revenue_summary", {"days": 30})
        if "outstanding" in r:
            sections.append(f"**Outstanding:** {_fmt_money(r['outstanding'])} across {r['outstanding_count']} unpaid "
                            f"records ({_fmt_money(r['overdue'])} overdue). → /dashboard/recovery?tab=outstanding")
    if _has(q, "recover"):
        r = execute(ctx, "revenue_summary", {"days": 30})
        if "recovered" in r:
            sections.append(f"**Recovered (last 30 days):** {_fmt_money(r['recovered'])} - each backed by a paid payment. "
                            f"Open opportunities are worth an estimated {_fmt_money(r['potential'])} (not revenue).")
    if _has(q, "expir", "renew"):
        days = 7 if "week" in q else 30
        r = execute(ctx, "list_expiring_memberships", {"days": days})
        if "memberships" in r:
            names = ", ".join(f"{m['member']} ({m['end_date']})" for m in r["memberships"][:8])
            sections.append(f"**{r['count']} memberships expire in the next {days} days**" + (f": {names}" if names else "")
                            + " → /dashboard/recovery?tab=renewals")
    if _has(q, "not been contacted", "uncontacted", "follow up", "follow-up", "contact today", "which leads"):
        r = execute(ctx, "leads_to_follow_up_today", {})
        if "leads" in r:
            sections.append(f"**{r['count']} leads to contact**\n" + "\n".join(
                f"- {l['name']} ({l['source'].replace('_', ' ')}, score {l['score']}): {l['why']}" for l in r["leads"][:10])
                + "\n→ /dashboard/leads")
    if _has(q, "trial"):
        t = execute(ctx, "trial_stats", {"days": 30})
        if "total" in t:
            rate = f"{t['attendance_rate']:.0%}" if t["attendance_rate"] is not None else "n/a"
            conv = f"{t['trial_to_membership']:.0%}" if t["trial_to_membership"] is not None else "n/a"
            sections.append(f"**Trials (30 days):** {t['total']} booked, {t['upcoming']} upcoming, {t['completed']} attended, "
                            f"{t['no_shows']} confirmed no-shows. Attendance {rate}, trial→member {conv}. → /dashboard/trials")
    if _has(q, "source", "channel", "marketing", "campaign", "where do", "paying members"):
        la = execute(ctx, "lead_analytics", {"days": 90})
        if "by_source" in la:
            rows = sorted(la["by_source"].items(), key=lambda kv: -kv[1]["revenue_collected"])
            sections.append("**Lead sources (90 days)**\n" + "\n".join(
                f"- {s.replace('_', ' ')}: {r['leads']} enquiries, {r['joined']} joined, {_fmt_money(r['revenue_collected'])} "
                "collected" for s, r in rows[:8]))
    if _has(q, "enquir", "how many leads", "leads did"):
        la = execute(ctx, "lead_analytics", {"days": 30})
        if "total_enquiries" in la:
            sections.append(f"**Enquiries (30 days):** {la['total_enquiries']} received, {la['uncontacted_now']} still "
                            f"uncontacted, {la['joined']} joined ({la['conversion_rate']:.0%}).")
    if _has(q, "seo", "website", "google search"):
        s = execute(ctx, "seo_status", {})
        if s.get("audited"):
            c = s.get("counts") or {}
            sections.append(f"**Website SEO:** score {s['score']}/100 (GymFlow checklist) for {s['url']}; "
                            f"{c.get('critical', 0)} critical, {c.get('high', 0)} high issues. Top: "
                            + "; ".join(i["title"] for i in s["top_issues"][:3]) + " → /dashboard/seo")
        elif "audited" in s:
            sections.append("No website audit yet - run one from Website SEO.")
    if _has(q, "local", "maps", "google business", "review", "local enquir"):
        lv = execute(ctx, "local_visibility", {})
        g = lv.get("google_business_profile")
        if g:
            sections.append(f"**Google Business Profile:** {g['connection'].replace('_', ' ')}; completeness "
                            f"{g['completeness'] if g['completeness'] is not None else 'not audited'}; "
                            f"{g['reviews_awaiting_reply']} reviews awaiting a reply. → /dashboard/local")
    if not sections or _has(q, "perform", "how is", "overview", "this month", "analy", "summary", "doing"):
        o = execute(ctx, "business_overview", {"days": datetime.now().day})
        if "active_members" in o:
            sections.insert(0, (
                f"**This month so far:** {o['active_members']} active members, {o['new_leads']} new leads, "
                f"{o['new_memberships']} new memberships, {_fmt_money(o['membership_revenue'])} collected, "
                f"{_fmt_money(o['recovered_revenue'])} recovered. {_fmt_money(o['outstanding'])} is outstanding and "
                f"{o['upcoming_renewals_30d']} memberships renew in the next 30 days."))
    if not sections:
        return "I couldn't find data for that. Try asking about leads, trials, renewals, payments, SEO or reviews."
    return "\n\n".join(sections)
