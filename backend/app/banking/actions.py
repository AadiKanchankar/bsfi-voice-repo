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


def investment_info(core: MockCore, customer_id: str, trace: ComplianceTrace,
                    slots: dict, transcript: str) -> dict:
    """Facts about a customer's own investments, or about a product.

    Everything here is a number that already exists in a record. Nothing here
    is a view on whether a holding is worth keeping: that is
    investment_advice, and it never reaches this function.
    """
    named = core.find_holding(customer_id, slots.get("product") or "")
    if named is None:
        for token in (transcript or "").replace(",", " ").split():
            if len(token) > 3:
                named = core.find_holding(customer_id, token)
                if named:
                    break
    if named:
        value = named["units"] * named["last_price"]
        units = named["units"]
        unit_word = {"equity": ("shares", "शेयर", "शेअर्स")}.get(
            named["kind"], ("units", "यूनिट", "युनिट्स"))
        return {
            "action_taken": "investment_info_holding",
            "result": {"holding": named, "value": round(value, 2)},
            "reply": {
                "en": f"You hold {units:g} {unit_word[0]} of {named['name']}, worth about "
                      f"{speech_amount(value, 'en')} at the last recorded price. "
                      f"That is a statement of fact, not a recommendation.",
                "hi": f"आपके पास {named['name']} के {units:g} {unit_word[1]} हैं, जिनकी क़ीमत "
                      f"पिछले दर्ज भाव पर लगभग {speech_amount(value, 'hi')} है। "
                      f"यह सिर्फ़ जानकारी है, कोई सलाह नहीं।",
                "mr": f"तुमच्याकडे {named['name']} चे {units:g} {unit_word[2]} आहेत, ज्यांची किंमत "
                      f"शेवटच्या नोंदवलेल्या दराने सुमारे {speech_amount(value, 'mr')} आहे. "
                      f"ही फक्त माहिती आहे, सल्ला नाही.",
            },
        }

    port = core.portfolio_value(customer_id)
    if not port["n_holdings"]:
        return {
            "action_taken": "investment_info_none",
            "result": port,
            "reply": {"en": "I do not see any investments held with us on this account.",
                      "hi": "इस खाते पर हमारे पास आपका कोई निवेश दर्ज नहीं है।",
                      "mr": "या खात्यावर आमच्याकडे तुमची कोणतीही गुंतवणूक नोंदलेली नाही."},
        }
    sips = core.get_sips(customer_id)
    sip_line = {
        "en": (f" You also have {len(sips)} active systematic plan"
               f"{'s' if len(sips) != 1 else ''}." if sips else ""),
        "hi": (f" आपकी {len(sips)} एसआईपी भी चल रही हैं।" if sips else ""),
        "mr": (f" तुमच्या {len(sips)} एसआयपी देखील सुरू आहेत." if sips else ""),
    }
    return {
        "action_taken": "investment_info_portfolio",
        "result": port | {"sips": sips},
        "reply": {
            "en": f"Across {port['n_holdings']} holdings your portfolio is worth about "
                  f"{speech_amount(port['value'], 'en')} at last recorded prices."
                  + sip_line["en"]
                  + " Past performance does not indicate future results.",
            "hi": f"आपके {port['n_holdings']} निवेशों की कुल क़ीमत पिछले दर्ज भावों पर लगभग "
                  f"{speech_amount(port['value'], 'hi')} है।" + sip_line["hi"]
                  + " पिछला प्रदर्शन भविष्य के नतीजों की गारंटी नहीं है।",
            "mr": f"तुमच्या {port['n_holdings']} गुंतवणुकींची एकूण किंमत शेवटच्या नोंदवलेल्या दरांनी सुमारे "
                  f"{speech_amount(port['value'], 'mr')} आहे." + sip_line["mr"]
                  + " मागील कामगिरी भविष्यातील निकालांची हमी देत नाही.",
        },
    }


def investment_advice(trace: ComplianceTrace) -> dict:
    """Refuse, explain, and hand to someone licensed to answer.

    Not a hedged answer. A hedged recommendation is still a recommendation,
    and under the SEBI Investment Advisers Regulations 2013 this assistant is
    not registered to give one. See POL-INV-016.
    """
    return {
        "action_taken": "escalate_to_investment_adviser",
        "result": {"reason": "investment advice requires a registered adviser",
                   "regulation": "SEBI (Investment Advisers) Regulations 2013",
                   "policy": "POL-INV-016", "automated_answer_given": False},
        "reply": {
            "en": ("I am not able to tell you what to buy or sell, or whether now is a "
                   "good time. Only a registered investment adviser can do that, and I "
                   "am not one. I can put you through to ours, and I can tell you the "
                   "facts about any product or about what you already hold."),
            "hi": ("क्या ख़रीदना या बेचना चाहिए, या अभी सही समय है या नहीं, यह मैं नहीं बता सकता। "
                   "यह सिर्फ़ पंजीकृत निवेश सलाहकार ही बता सकते हैं, और मैं वह नहीं हूँ। मैं आपको "
                   "हमारे सलाहकार से जोड़ सकता हूँ, और किसी भी उत्पाद या आपके मौजूदा निवेश की "
                   "जानकारी दे सकता हूँ।"),
            "mr": ("काय खरेदी करावे किंवा विकावे, किंवा आताची वेळ योग्य आहे का, हे मी सांगू शकत नाही. "
                   "हे फक्त नोंदणीकृत गुंतवणूक सल्लागारच सांगू शकतात, आणि मी तो नाही. मी तुम्हाला "
                   "आमच्या सल्लागाराकडे जोडू शकतो, आणि कोणत्याही उत्पादनाची किंवा तुमच्या सध्याच्या "
                   "गुंतवणुकीची माहिती देऊ शकतो."),
        },
    }


# ---------------------------------------------------------------- tier 3

# What each intent is called when the assistant has to name it out loud.
# Used to offer "did you mean X or Y" in the caller's own terms rather than
# reading an internal label at them.
_INTENT_WORDS = {
    "get_balance": {"en": "your balance", "hi": "आपका बैलेंस", "mr": "तुमचा बॅलन्स"},
    "mini_statement": {"en": "your recent transactions",
                       "hi": "आपके हाल के लेनदेन", "mr": "तुमचे अलीकडील व्यवहार"},
    "cheque_status": {"en": "a cheque", "hi": "एक चेक", "mr": "एक धनादेश"},
    "branch_ifsc": {"en": "a branch or IFSC code",
                    "hi": "शाखा या IFSC कोड", "mr": "शाखा किंवा IFSC कोड"},
    "product_info": {"en": "our rates and products",
                     "hi": "हमारी दरें और उत्पाद", "mr": "आमचे दर आणि उत्पादने"},
    "block_card": {"en": "blocking a card", "hi": "कार्ड ब्लॉक करना",
                   "mr": "कार्ड ब्लॉक करणे"},
    "fund_transfer": {"en": "a transfer", "hi": "एक भुगतान", "mr": "एक व्यवहार"},
    "investment_info": {"en": "your investments", "hi": "आपके निवेश",
                        "mr": "तुमची गुंतवणूक"},
}


def clarify(trace: ComplianceTrace, options: list[str], attempt: int) -> dict:
    """Ask one short question instead of transferring the call.

    Two shapes, depending on what is unclear. If the reading narrowed to a
    couple of plausible intents, name them and let the caller pick. If it did
    not narrow at all, say plainly that it was not understood and ask again,
    because offering a guess nobody made is worse than admitting it.

    Never more than two options. A spoken menu of five is a phone tree, and
    the whole point of this system is not being one.
    """
    named = [_INTENT_WORDS[o] for o in options if o in _INTENT_WORDS][:2]

    if len(named) >= 2:
        a, b = named[0], named[1]
        reply = {
            "en": f"I can help with {a['en']} or {b['en']}. Which would you like?",
            "hi": f"मैं {a['hi']} या {b['hi']} में मदद कर सकता हूँ। आप क्या चाहेंगे?",
            "mr": f"मी {a['mr']} किंवा {b['mr']} मध्ये मदत करू शकतो. तुम्हाला काय हवे?",
        }
    elif named:
        a = named[0]
        reply = {
            "en": f"Did you want {a['en']}?",
            "hi": f"क्या आपको {a['hi']} चाहिए?",
            "mr": f"तुम्हाला {a['mr']} हवे आहे का?",
        }
    else:
        reply = {
            "en": "Sorry, I did not quite catch that. Could you say it again?",
            "hi": "माफ़ कीजिए, मैं समझ नहीं पाया। क्या आप दोबारा कह सकते हैं?",
            "mr": "माफ करा, मला नीट समजले नाही. तुम्ही पुन्हा सांगाल का?",
        }
    return {"action_taken": "clarify",
            "result": {"options": options[:2], "attempt": attempt},
            "reply": reply}


def split_compound(trace: ComplianceTrace, first: str, lang: str) -> dict:
    """Two things were asked at once. Say so, and take them in order.

    Better than clarifying: the caller told us both halves, so asking which
    one they meant is asking them to repeat themselves. Answer the first and
    say the second is coming.
    """
    a = _INTENT_WORDS.get(first, {}).get(lang) or _INTENT_WORDS.get(first, {}).get("en", "that")
    return {"action_taken": "split_compound",
            "result": {"handling_first": first},
            "reply": {
                "en": f"You asked for two things. Let me start with {a}.",
                "hi": f"आपने दो चीज़ें पूछी हैं। पहले {a} बताता हूँ।",
                "mr": f"तुम्ही दोन गोष्टी विचारल्या. आधी {a} सांगतो.",
            }}


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
        # Two different sentences, not one sentence with a hole in it. The
        # fallback used to be substituted into the phrase "the card ending
        # {x}", which produced "the card ending on file": ungrammatical, and
        # on the most safety-critical sentence the assistant ever speaks,
        # the one a caller says yes to before a card is blocked.
        l4 = slots.get("card_last4")
        if l4:
            return (f"You want me to permanently block the card ending "
                    f"{speech_digits(l4, 'en')}.",
                    f"आप {speech_digits(l4, 'hi')} पर खत्म होने वाला कार्ड हमेशा के "
                    f"लिए बंद कराना चाहते हैं।",
                    f"तुम्हाला {speech_digits(l4, 'mr')} वर संपणारे कार्ड कायमचे बंद "
                    f"करायचे आहे.")
        return ("You want me to permanently block the card registered on your "
                "account.",
                "आप अपने खाते में पंजीकृत कार्ड हमेशा के लिए बंद कराना चाहते हैं।",
                "तुम्हाला तुमच्या खात्यावर नोंदणीकृत कार्ड कायमचे बंद करायचे आहे.")
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
