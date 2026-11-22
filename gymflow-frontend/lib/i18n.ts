"use client";

import { useEffect, useState } from "react";

/**
 * Tiny translation layer for the owner's main screens. English text is the key, so anything not yet translated
 * simply shows in English. Add a language by adding a dictionary below.
 */
export type Lang = "en" | "hi";
export const LANGS: { value: Lang; label: string }[] = [{ value: "en", label: "English" }, { value: "hi", label: "हिंदी" }];

const HI: Record<string, string> = {
  // navigation
  "Today": "आज", "Members": "मेंबर्स", "Enquiries": "पूछताछ", "Money": "पैसे", "Grow": "बढ़ाएँ", "Settings": "सेटिंग्स",
  "My members": "मेरे मेंबर्स", "Check-in": "चेक-इन", "Trials": "ट्रायल", "My tasks": "मेरे काम",
  "All members": "सभी मेंबर्स", "Plans & prices": "प्लान और कीमतें", "Inbox": "इनबॉक्स", "Board": "बोर्ड",
  "Follow-ups": "फॉलो-अप", "Insights": "जानकारी", "Due now": "अभी बाकी", "Payments": "पेमेंट",
  "Renewal history": "रिन्यूअल इतिहास", "Reports": "रिपोर्ट", "Overview": "सारांश", "Google & reviews": "Google और रिव्यू",
  "Website health": "वेबसाइट की सेहत", "My website": "मेरी वेबसाइट", "AI receptionist": "AI रिसेप्शनिस्ट",
  "ChatGPT & AI search": "ChatGPT और AI सर्च", "Gym profile": "जिम प्रोफ़ाइल", "Info for AI replies": "AI जवाबों के लिए जानकारी",
  "Team": "टीम", "Reminders": "रिमाइंडर", "Connections": "कनेक्शन", "AI settings": "AI सेटिंग्स", "Subscription": "सब्सक्रिप्शन",
  "Help on WhatsApp": "WhatsApp पर मदद", "Add member": "मेंबर जोड़ें", "Take payment": "पेमेंट लें",
  "Check someone in": "चेक-इन करें", "Add enquiry": "पूछताछ जोड़ें",
  // today
  "Good morning": "सुप्रभात", "Good afternoon": "नमस्ते", "Good evening": "शुभ संध्या",
  "Waiting to be collected": "वसूली बाकी", "See who owes": "देखें किसका बाकी है",
  "Brought back by GymFlow this month": "इस महीने GymFlow ने वापस दिलाए",
  "Nobody owes you anything right now.": "अभी किसी का कुछ बाकी नहीं है।",
  "{n} people": "{n} लोग", "{n} person": "{n} व्यक्ति", "{n} late": "{n} लेट", "{n} ending this week": "{n} इस हफ़्ते खत्म",
  "That's {x}× what you pay for GymFlow ({price}/month).": "यह GymFlow की फ़ीस ({price}/महीना) का {x}× है।",
  "Do these today": "आज ये करें", "{n} to do": "{n} काम", "All done for today": "आज के सारे काम पूरे",
  "Nobody is late and every enquiry has a reply. Nice work.": "कोई लेट नहीं और हर पूछताछ का जवाब दिया गया। बढ़िया!",
  "See all {n} people who owe money →": "पैसे बाकी वाले सभी {n} लोग देखें →",
  "Active members": "एक्टिव मेंबर्स", "New joins this month": "इस महीने नए मेंबर", "Collected this month": "इस महीने वसूली",
  "Check-ins this month": "इस महीने चेक-इन", "Ask anything about your gym…": "अपने जिम के बारे में कुछ भी पूछें…", "Ask": "पूछें",
  "Finish setting up your gym": "अपना जिम सेटअप पूरा करें", "Sample gym · demo data": "सैंपल जिम · डेमो डेटा",
  // money
  "Who owes you money": "किसका पैसा बाकी है", "Late": "लेट", "Ending this week": "इस हफ़्ते खत्म", "Ending this month": "इस महीने खत्म",
  "Remind": "याद दिलाएँ", "Paid": "मिल गया", "Cancel": "रद्द करें", "Cash": "कैश", "UPI": "UPI", "Card": "कार्ड",
  "Remind {n} on WhatsApp": "{n} लोगों को WhatsApp पर याद दिलाएँ", "Nobody owes you money": "किसी का पैसा बाकी नहीं",
  "Open WhatsApp & next": "WhatsApp खोलें और अगला", "Skip": "छोड़ें",
  "membership ends today": "मेंबरशिप आज खत्म", "fee due": "फ़ीस बाकी", "online payment failed": "ऑनलाइन पेमेंट फ़ेल",
  "membership {d} days left": "मेंबरशिप के {d} दिन बाकी", "membership ended {d} days ago": "मेंबरशिप {d} दिन पहले खत्म",
  "fee {d} days late": "फ़ीस {d} दिन लेट", "reminded {n}×": "{n}× याद दिलाया",
};

const DICTS: Record<Lang, Record<string, string>> = { en: {}, hi: HI };
const KEY = "gf-lang";
const EVENT = "gf-lang-change";

export function getLang(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    return v === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

export function setLang(lang: Lang) {
  try { localStorage.setItem(KEY, lang); } catch { /* private mode */ }
  document.documentElement.lang = lang;
  window.dispatchEvent(new Event(EVENT));
}

export function translate(lang: Lang, text: string, vars?: Record<string, string | number>) {
  let out = DICTS[lang][text] ?? text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
  return out;
}

/** ``t("Remind {n} on WhatsApp", { n: 4 })`` – re-renders when the language changes anywhere on the page. */
export function useT() {
  const [lang, setL] = useState<Lang>("en");
  useEffect(() => {
    const sync = () => setL(getLang());
    sync();
    window.addEventListener(EVENT, sync);
    return () => window.removeEventListener(EVENT, sync);
  }, []);
  const t = (text: string, vars?: Record<string, string | number>) => translate(lang, text, vars);
  return { t, lang };
}
