"""One function per intent. Each returns the reply in three languages plus the
structured result that goes into the trace.

Replies are templates, not generation. A template cannot hallucinate an
interest rate, and every grounded answer names its source document.

Two rules learned from listening to a recording of the thing talking:

**Hindi and Marathi are written in Devanagari.** Both speech engines
phonemise from script, so a romanised reply is read with English vowels and
comes out sounding like neither language. pipeline/tts.py refuses to speak a
romanised Hindi string, so this is enforced rather than remembered.

**Say numbers the way a person would.** A balance is "two lakh six thousand
four hundred and sixty five rupees", not "206,465.68", and an account ending
2902 is "two nine zero two", not "two thousand nine hundred and two". The
digits stay exact in `result`, which is what the dashboard and the ledger see.
"""
from __future__ import annotations

from ..config import OTP_DEMO_CODE
from ..pipeline.speech_text import speech_amount, speech_digits
from ..trace import ComplianceTrace, RetrievedPassage
from .mock_core import MockCore

Reply = dict[str, str]        # language code -> text

LANGS = ("en", "hi", "mr")


def _amt(value: float) -> str:
    """Exact digits, for the trace and the dashboard."""
    return f"{value:,.2f}"


def pick(reply: Reply, lang: str) -> str:
    return reply.get(lang) or reply.get("en") or next(iter(reply.values()))


def _per_lang(build) -> Reply:
    """Build the same sentence in all three languages from one callable."""
    return {lang: build(lang) for lang in LANGS}


# ---------------------------------------------------------------- tier 0, grounded

def _cite(passages: list[RetrievedPassage]) -> Reply:
    """Spoken citation.

    The document title and version are said aloud; the identifier is not.
    Reading "P O L hyphen H L hyphen zero zero one" at a customer is the
    single most robotic thing the assistant used to do, and the exact id is
    one click away on the dashboard, where an auditor actually wants it.
    """
    if not passages:
        return {lang: "" for lang in LANGS}
    p = passages[0]
    title = (p.text.split(".")[0] or p.section).strip()
    return {
        "en": f" That is from our {title.lower()} policy, version {p.version}.",
        "hi": f" यह जानकारी हमारी नीति के संस्करण {p.version} से है।",
        "mr": f" ही माहिती आमच्या धोरणाच्या आवृत्ती {p.version} मधून आहे.",
    }


def answer_from_policy(trace: ComplianceTrace) -> dict:
    passages = trace.retrieved
    if not passages:
        return refuse(trace, "no policy passage cleared the similarity floor")
    body = passages[0].text
    sentences = [s.strip() for s in body.split(". ") if s.strip()]
    heading, content = (sentences[0], sentences[1:]) if len(sentences) > 1 else ("", sentences)
    spoken = ". ".join(content[:2])
    if len(spoken) > 400:
        spoken = spoken[:400].rsplit(" ", 1)[0] + ", and there is more detail in the document"
    spoken = f"{spoken}." if spoken.endswith((".", "!", "?")) is False else spoken
    cite = _cite(passages)
    # The body of a policy passage is English in this knowledge base. Saying so
    # is more honest than pretending to answer in the caller's language, and
    # the caller still gets the framing in their own.
    lead = {"en": "", "hi": "यह हमारी नीति में इस तरह लिखा है। ",
            "mr": "आमच्या धोरणात हे असे लिहिले आहे. "}
    return {
        "action_taken": "answer_from_policy",
        "result": {"doc_id": passages[0].doc_id, "version": passages[0].version,
                   "section": passages[0].section, "score": passages[0].score,
                   "citations": [{"doc_id": p.doc_id, "version": p.version,
                                  "section": p.section, "score": p.score}
                                 for p in passages]},
        "reply": {lang: f"{lead[lang]}{spoken}{cite[lang]}" for lang in LANGS},
    }


def refuse(trace: ComplianceTrace, reason: str) -> dict:
    score, floor = trace.retrieval_max_score, trace.retrieval_floor
    detail = ""
    if score is not None and floor is not None:
        detail = f" The closest thing I have on file was not a close enough match."
    return {
        "action_taken": "refuse",
        "result": {"reason": reason, "max_score": score, "floor": floor},
        "reply": {
            "en": ("I do not have a verified answer to that, so I am not going to guess."
                   + detail + " I can put you through to a colleague who can help."),
            "hi": ("इसका पुष्ट उत्तर मेरे पास नहीं है, इसलिए मैं अंदाज़ा नहीं लगाऊँगा। "
                   "मैं आपको किसी सहकर्मी से जोड़ सकता हूँ जो मदद कर सकें।"),
            "mr": ("याचे खात्रीशीर उत्तर माझ्याकडे नाही, म्हणून मी अंदाज करणार नाही. "
                   "मी तुम्हाला मदत करू शकणाऱ्या सहकाऱ्याकडे जोडू शकतो."),
        },
    }


# ---------------------------------------------------------------- tier 1

def get_balance(core: MockCore, customer_id: str, trace: ComplianceTrace) -> dict:
    acct = core.primary_account(customer_id)
    if not acct:
        return refuse(trace, "no account on file")
    bal = core.get_balance(acct["account_id"])
    last4 = acct["account_number"][-4:]
    kind = {"en": bal["account_type"], "hi": "बचत" if bal["account_type"] == "savings" else "चालू",
            "mr": "बचत" if bal["account_type"] == "savings" else "चालू"}
    return {
        "action_taken": "get_balance",
        "result": {"account_last4": last4, "balance": bal["balance"],
                   "balance_formatted": _amt(bal["balance"]),
                   "account_type": bal["account_type"]},
        "reply": {
            "en": f"Your {kind['en']} account ending {speech_digits(last4, 'en')} "
                  f"has {speech_amount(bal['balance'], 'en')}.",
            "hi": f"{speech_digits(last4, 'hi')} पर खत्म होने वाले आपके {kind['hi']} खाते में "
                  f"{speech_amount(bal['balance'], 'hi')} हैं।",
            "mr": f"{speech_digits(last4, 'mr')} वर संपणाऱ्या तुमच्या {kind['mr']} खात्यात "
                  f"{speech_amount(bal['balance'], 'mr')} आहेत.",
        },
    }


def mini_statement(core: MockCore, customer_id: str, trace: ComplianceTrace,
                   limit: int = 3) -> dict:
    acct = core.primary_account(customer_id)
    if not acct:
        return refuse(trace, "no account on file")
    txns = core.get_transactions(acct["account_id"], limit)
    if not txns:
        return {"action_taken": "mini_statement", "result": {"count": 0, "transactions": []},
                "reply": {"en": "I do not see any recent transactions on that account.",
                          "hi": "उस खाते में मुझे कोई हालिया लेनदेन नहीं दिख रहा।",
                          "mr": "त्या खात्यात मला अलीकडचे कोणतेही व्यवहार दिसत नाहीत."}}

    direction = {"en": {"debit": "out", "credit": "in"},
                 "hi": {"debit": "निकाले गए", "credit": "जमा हुए"},
                 "mr": {"debit": "काढले गेले", "credit": "जमा झाले"}}

    def line(t: dict, lang: str) -> str:
        amount = speech_amount(t["amount"], lang)
        day = t["ts"][8:10].lstrip("0")
        if lang == "en":
            return f"on the {day}th, {amount} {direction['en'][t['direction']]}"
        if lang == "hi":
            return f"{day} तारीख़ को {amount} {direction['hi'][t['direction']]}"
        return f"{day} तारखेला {amount} {direction['mr'][t['direction']]}"

    joiner = {"en": ", then ", "hi": ", फिर ", "mr": ", नंतर "}
    lead = {"en": f"Here are your last {len(txns)} transactions. ",
            "hi": f"आपके पिछले {len(txns)} लेनदेन ये हैं। ",
            "mr": f"तुमचे शेवटचे {len(txns)} व्यवहार असे आहेत. "}
    return {
        "action_taken": "mini_statement",
        "result": {"account_last4": acct["account_number"][-4:], "count": len(txns),
                   "transactions": txns},
        "reply": {lang: lead[lang] + joiner[lang].join(line(t, lang) for t in txns) + "."
                  for lang in LANGS},
    }


def cheque_status(core: MockCore, customer_id: str, trace: ComplianceTrace,
                  cheque_number: str | None) -> dict:
    if not cheque_number:
        return {
            "action_taken": "cheque_status_need_slot",
            "result": {"missing_slot": "cheque_number"},
            "reply": {"en": "Could you tell me the cheque number, and I will check it.",
                      "hi": "आप चेक नंबर बता दीजिए, मैं जाँच कर देता हूँ।",
                      "mr": "तुम्ही चेक क्रमांक सांगा, मी तपासतो."},
        }
    chq = core.get_cheque(cheque_number)
    if not chq:
        return refuse(trace, f"cheque {cheque_number} not found")
    status = {
        "cleared": {"en": "has cleared", "hi": "क्लियर हो चुका है", "mr": "क्लिअर झाला आहे"},
        "pending": {"en": "is still pending", "hi": "अभी लंबित है", "mr": "अजून प्रलंबित आहे"},
    }.get(chq["status"], {"en": f"is marked {chq['status']}",
                          "hi": "वापस आ गया है, खाते में पर्याप्त राशि नहीं थी",
                          "mr": "परत आला आहे, खात्यात पुरेशी रक्कम नव्हती"})
    return {
        "action_taken": "cheque_status",
        "result": chq,
        "reply": {
            "en": f"Cheque {speech_digits(cheque_number, 'en')}, for "
                  f"{speech_amount(chq['amount'], 'en')}, {status['en']}.",
            "hi": f"चेक {speech_digits(cheque_number, 'hi')}, "
                  f"{speech_amount(chq['amount'], 'hi')} का, {status['hi']}।",
            "mr": f"चेक {speech_digits(cheque_number, 'mr')}, "
                  f"{speech_amount(chq['amount'], 'mr')} चा, {status['mr']}.",
        },
    }


def branch_ifsc(core: MockCore, trace: ComplianceTrace, query: str) -> dict:
    branches = core.find_branch(query)
    if not branches:
        return answer_from_policy(trace)
    b = branches[0]
    ifsc = " ".join(b["ifsc"])         # spelled out, it is a code not a word
    return {
        "action_taken": "branch_ifsc",
        "result": {"matches": branches},
        "reply": {
            "en": f"The {b['name']} branch is at {b['address']}. Its I F S C code is {ifsc}.",
            "hi": f"{b['name']} शाखा {b['address']} पर है। इसका आई एफ एस सी कोड {ifsc} है।",
            "mr": f"{b['name']} शाखा {b['address']} येथे आहे. तिचा आय एफ एस सी कोड {ifsc} आहे.",
        },
    }


# ---------------------------------------------------------------- tier 2

def block_card(core: MockCore, customer_id: str, trace: ComplianceTrace,
               last4: str | None) -> dict:
    card = core.find_card(customer_id, last4)
    if not card:
        return refuse(trace, "no matching card on file")
    out = core.block_card(card["card_id"])
    d = speech_digits(out["last4"], "en")
    return {
        "action_taken": "block_card",
        "result": out,
        "reply": {
            "en": f"Done. Your {card['card_type']} card ending {d} is blocked now. "
                  f"A replacement goes out within seven working days.",
            "hi": f"हो गया। {speech_digits(out['last4'], 'hi')} पर खत्म होने वाला आपका कार्ड "
                  f"अब बंद कर दिया गया है। नया कार्ड सात कार्य दिवसों में भेज दिया जाएगा।",
            "mr": f"झाले. {speech_digits(out['last4'], 'mr')} वर संपणारे तुमचे कार्ड "
                  f"आता बंद केले आहे. नवीन कार्ड सात कामकाजाच्या दिवसांत पाठवले जाईल.",
        },
    }


def limit_change(core: MockCore, customer_id: str, trace: ComplianceTrace,
                 last4: str | None, amount: float | None) -> dict:
    if not amount:
        return {"action_taken": "limit_change_need_slot",
                "result": {"missing_slot": "amount"},
                "reply": {"en": "What would you like the new daily limit to be?",
                          "hi": "आप नई दैनिक सीमा कितनी रखना चाहेंगे?",
                          "mr": "तुम्हाला नवीन दैनिक मर्यादा किती ठेवायची आहे?"}}
    card = core.find_card(customer_id, last4)
    if not card:
        return refuse(trace, "no matching card on file")
    out = core.set_card_limit(card["card_id"], amount)
    l4 = card["card_number"][-4:]
    return {
        "action_taken": "limit_change",
        "result": out | {"last4": l4, "amount_formatted": _amt(amount)},
        "reply": {
            "en": f"The daily limit on the card ending {speech_digits(l4, 'en')} is now "
                  f"{speech_amount(amount, 'en')}.",
            "hi": f"{speech_digits(l4, 'hi')} पर खत्म होने वाले कार्ड की दैनिक सीमा अब "
                  f"{speech_amount(amount, 'hi')} है।",
            "mr": f"{speech_digits(l4, 'mr')} वर संपणाऱ्या कार्डाची दैनिक मर्यादा आता "
                  f"{speech_amount(amount, 'mr')} आहे.",
        },
    }


def add_payee(core: MockCore, customer_id: str, trace: ComplianceTrace,
              name: str | None, account_number: str | None) -> dict:
    if not name:
        return {"action_taken": "add_payee_need_slot",
                "result": {"missing_slot": "payee"},
                "reply": {"en": "What name should I add the payee under?",
                          "hi": "मैं किस नाम से भुगतान पाने वाले को जोड़ूँ?",
                          "mr": "मी कोणत्या नावाने लाभार्थी जोडू?"}}
    out = core.add_payee(customer_id, name, account_number or "000000000000")
    return {
        "action_taken": "add_payee",
        "result": out,
        "reply": {
            "en": f"I have added {name}. Transfers to a new payee open up after a "
                  f"thirty minute cooling period.",
            "hi": f"मैंने {name} को जोड़ दिया है। नए लाभार्थी को पैसे भेजना तीस मिनट बाद "
                  f"शुरू हो सकेगा।",
            "mr": f"मी {name} यांना जोडले आहे. नवीन लाभार्थ्याला पैसे पाठवणे तीस मिनिटांनंतर "
                  f"सुरू होईल.",
        },
    }


def fund_transfer(core: MockCore, customer_id: str, trace: ComplianceTrace,
                  payee: str | None, amount: float | None) -> dict:
    if not amount or not payee:
        missing = {"en": "amount" if not amount else "payee name",
                   "hi": "राशि" if not amount else "लाभार्थी का नाम",
                   "mr": "रक्कम" if not amount else "लाभार्थ्याचे नाव"}
        return {"action_taken": "fund_transfer_need_slot",
                "result": {"missing_slot": "amount" if not amount else "payee"},
                "reply": {"en": f"I need the {missing['en']} before I can make that transfer.",
                          "hi": f"यह भुगतान करने से पहले मुझे {missing['hi']} चाहिए।",
                          "mr": f"हे पैसे पाठवण्यापूर्वी मला {missing['mr']} हवे."}}
    acct = core.primary_account(customer_id)
    matches = [p for p in core.get_payees(customer_id) if p["name"].lower() == payee.lower()]
    if not matches:
        return refuse(trace, f"payee {payee} is not registered")
    out = core.transfer(acct["account_id"], matches[0]["payee_id"], amount)
    if out["status"] != "completed":
        return {"action_taken": "fund_transfer_declined", "result": out,
                "reply": {"en": "That transfer did not go through, there are not enough "
                                "funds in the account.",
                          "hi": "यह भुगतान नहीं हो पाया, खाते में पर्याप्त राशि नहीं है।",
                          "mr": "हे पैसे पाठवता आले नाहीत, खात्यात पुरेशी रक्कम नाही."}}
    ref = " ".join(out["txn_id"][-4:])
    return {
        "action_taken": "fund_transfer",
        "result": out | {"amount_formatted": _amt(amount)},
        "reply": {
            "en": f"Sent. {speech_amount(amount, 'en')} to {payee}. "
                  f"The reference ends {ref}.",
            "hi": f"भेज दिया। {payee} को {speech_amount(amount, 'hi')}। "
                  f"संदर्भ संख्या {ref} पर खत्म होती है।",
            "mr": f"पाठवले. {payee} यांना {speech_amount(amount, 'mr')}. "
                  f"संदर्भ क्रमांक {ref} वर संपतो.",
        },
    }


# ---------------------------------------------------------------- tier 3

def escalate(trace: ComplianceTrace, reason: str, queue_position: int = 1) -> dict:
    return {
        "action_taken": "escalate_to_agent",
        "result": {"reason": reason, "queue_position": queue_position,
                   "context_packet": "attached"},
        "reply": {
            "en": ("I am putting you through to a colleague now. I have passed on "
                   "everything we discussed, so you will not have to start again. "
                   "Nothing has been changed on your account."),
            "hi": ("मैं आपको अभी एक सहकर्मी से जोड़ रहा हूँ। हमारी पूरी बातचीत मैंने आगे भेज दी है, "
                   "इसलिए आपको दोबारा शुरू से बताना नहीं पड़ेगा। आपके खाते में कोई बदलाव नहीं किया गया है।"),
            "mr": ("मी तुम्हाला आता एका सहकाऱ्याकडे जोडत आहे. आपले संपूर्ण संभाषण मी पुढे पाठवले आहे, "
                   "त्यामुळे तुम्हाला पुन्हा सुरुवातीपासून सांगावे लागणार नाही. तुमच्या खात्यात कोणताही बदल केलेला नाही."),
        },
    }


# ---------------------------------------------------------------- friction

def request_otp(intent: str) -> dict:
    return {
        "action_taken": "request_otp",
        "result": {"otp_required": True, "channel": "SIMULATED", "demo_code": OTP_DEMO_CODE},
        "reply": {
            "en": "Because this changes something on your account, I need a one time "
                  "password. Please read out the six digit code we have just sent to "
                  "your registered mobile number.",
            "hi": "चूँकि इससे आपके खाते में बदलाव होगा, मुझे एक बार का पासवर्ड चाहिए। "
                  "आपके पंजीकृत मोबाइल नंबर पर अभी भेजा गया छह अंकों का कोड बता दीजिए।",
            "mr": "यामुळे तुमच्या खात्यात बदल होणार असल्याने मला एक वेळचा पासवर्ड हवा आहे. "
                  "तुमच्या नोंदणीकृत मोबाइल क्रमांकावर आत्ताच पाठवलेला सहा अंकी कोड सांगा.",
        },
    }


def readback(summary_en: str, summary_hi: str, summary_mr: str) -> dict:
    return {
        "action_taken": "readback",
        "result": {"readback": summary_en},
        "reply": {
            "en": f"Let me confirm before I do it. {summary_en} Say yes and I will go ahead.",
            "hi": f"करने से पहले एक बार पुष्टि कर लें। {summary_hi} हाँ कहिए, मैं आगे बढ़ता हूँ।",
            "mr": f"करण्यापूर्वी एकदा खात्री करू. {summary_mr} होय म्हणा, मी पुढे जातो.",
        },
    }


def readback_summary(intent: str, slots: dict) -> tuple[str, str, str]:
    if intent == "block_card":
        l4 = slots.get("card_last4")
        en = speech_digits(l4, "en") if l4 else "on file"
        hi = speech_digits(l4, "hi") if l4 else "आपके"
        mr = speech_digits(l4, "mr") if l4 else "तुमचे"
        return (f"You want me to permanently block the card ending {en}.",
                f"आप {hi} पर खत्म होने वाला कार्ड हमेशा के लिए बंद कराना चाहते हैं।",
                f"तुम्हाला {mr} वर संपणारे कार्ड कायमचे बंद करायचे आहे.")
    if intent == "fund_transfer":
        a, p = slots.get("amount", 0), slots.get("payee", "the payee")
        return (f"You want me to send {speech_amount(a, 'en')} to {p}.",
                f"आप {p} को {speech_amount(a, 'hi')} भेजना चाहते हैं।",
                f"तुम्हाला {p} यांना {speech_amount(a, 'mr')} पाठवायचे आहेत.")
    if intent == "limit_change":
        a = slots.get("amount", 0)
        return (f"You want your daily limit set to {speech_amount(a, 'en')}.",
                f"आप दैनिक सीमा {speech_amount(a, 'hi')} करना चाहते हैं।",
                f"तुम्हाला दैनिक मर्यादा {speech_amount(a, 'mr')} करायची आहे.")
    return ("You want me to go ahead with that.",
            "आप चाहते हैं कि मैं यह कर दूँ।",
            "तुम्हाला मी हे करावे असे वाटते.")


def out_of_scope(trace: ComplianceTrace) -> dict:
    return refuse(trace, "the request is outside what this assistant is allowed to answer")


def need_verification(reason: str = "") -> dict:
    return {
        "action_taken": "request_verification",
        "result": {"verification_required": True, "reason": reason},
        "reply": {
            "en": "Before we talk about your account I need to check your voice. "
                  "Tap the microphone and say: my voice is my password.",
            "hi": "आपके खाते की बात करने से पहले मुझे आपकी आवाज़ जाँचनी होगी। "
                  "माइक दबाकर कहिए: मेरी आवाज़ ही मेरा पासवर्ड है।",
            "mr": "तुमच्या खात्याबद्दल बोलण्यापूर्वी मला तुमचा आवाज तपासावा लागेल. "
                  "माइक दाबून म्हणा: माझा आवाजच माझा पासवर्ड आहे.",
        },
    }
