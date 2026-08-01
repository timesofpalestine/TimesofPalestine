#!/usr/bin/env python3
"""Builds the English and Arabic article pages for timesofpalestine.com.

Figures are rendered as HTML/CSS rather than images so that Arabic shapes and
reorders correctly in every browser, the text stays selectable and indexable,
and the layouts reflow on a phone.
"""
import os, re, markdown

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "site")

# ---------------------------------------------------------------- figure data
FIGS = {
    "en": {
        1: dict(
            n="Figure 1", kicker="THE LEDGER OF FIGURES",
            title="What Suha Arafat was said to receive",
            sub="Alleged monthly payments in circulation, 2003\u20132020. Same person, same period, same currency.",
            head=["Alleged per month", "Who said it", "Evidence produced"],
            rows=[("$200,000", 100, "US newsmagazine, Nov 2004 \u2014 \u201Cpeople familiar with Arafat\u2019s finances\u201D", 0, "No source produced"),
                  ("$100,000", 50, "US network television, Nov 2003 \u2014 Israeli officials; later an unnamed PA official", 0, "No source produced"),
                  ("$50,000", 25, "Arabic press, 2011 \u2014 unattributed; she denied it specifically", 0, "No source produced"),
                  ("$12,000", 6, "Suha Arafat, Asharq Al-Awsat, 2011 \u2014 plus rent, described as the PLO pension", 1, "Named, on the record"),
                  ("\u20AC10,000", 6, "Suha Arafat, Israeli broadcaster Kan, 2020 \u2014 the same account, nine years later", 1, "Named, on the record")],
            punch="A sixteen-fold spread. They cannot all be true.",
            note="Separately, a figure of $22 million per year \u2014 a supposed settlement paid from secret accounts \u2014 has circulated since 2004, attributed to unnamed Palestinian officials. The agreement has never been produced.",
            src="Compiled from contemporaneous wire and broadcast reporting, 2003\u20132020."),
        2: dict(
            n="Figure 2", kicker="CLAIM VS. RECORD",
            title="What was announced, and what was ever established",
            sub="Six claims that shaped the public memory of the Arafat family finances.",
            head=["As it circulated", "What the record shows"],
            rows=[("Suha Arafat was investigated for money laundering in France", "Preliminary inquiry opened October 2003. French officials stated the illicit-origin threshold was not met. No formal investigation, no charge, no public disposition, ever.", 0),
                  ("She lived on an entire floor of a five-star Paris hotel", "The hotel said she had never stayed there. The denial was published. The claim continued to circulate unchanged.", 0),
                  ("She received $100,000 a month from Palestinian funds", "No bank record, transfer instruction, budget line or named source has been produced in twenty-two years.", 0),
                  ("Zahwa Arafat is worth $8 billion and owns London property", "No filing, registry entry, audit or court record exists. The same post places her in Paris; she has lived in Malta since childhood.", 0),
                  ("She was subject to a Tunisian arrest warrant", "Correct. Issued October 2011 over a private school venture with the Ben Ali family\u2019s circle \u2014 a Tunisian commercial matter, not Palestinian public money.", 1),
                  ("$900 million of Palestinian revenue was diverted, 1995\u20132000", "Correct, per the IMF. Into an account controlled by Yasser Arafat. Most of the traced portion was recovered under Salam Fayyad\u2019s reforms.", 1)],
            key=["Unevidenced or contradicted", "Documented"],
            src="Sources: Paris prosecutor statements 2003\u201304; IMF, September 2003; Tunisian Justice Ministry, October 2011; wire reporting."),
        3: dict(
            n="Figure 3", kicker="THE MARKET FOR A STORY",
            title="Four buyers, and what each one got",
            sub="A smear is not a mistake. It is a product, and products have buyers.",
            l1="What they put into circulation", l2="What it bought them",
            cols=[("The Israeli government", "2002\u20132004", "Military intelligence briefs the Knesset that Arafat personally controls $1.3bn. Israeli officials are the sourcing behind the $100,000-a-month figure.", "Converts a national leadership into a criminal enterprise. Once a movement is a racket, the question of what it is owed politically stops being asked."),
                  ("The PA and Fatah old guard", "2004\u2013present", "The largest and least sourced figures \u2014 $22m a year, \u201Chundreds of millions inherited\u201D \u2014 are attributed to unnamed Palestinian officials, not Israeli ones.", "Neutralises a widow who had criticised PA corruption publicly, controlled access to the dying president, and knew where accounts were."),
                  ("Ben Ali\u2019s Tunisia", "2007\u20132011", "Strips her citizenship by decree after she disparages the ruling family to the US ambassador. Post-revolution, her name joins the Trabelsi dragnet.", "Removes an inconvenient guest, then supplies the world with a court document that reads, at a glance, as proof of everything else."),
                  ("The content economy", "2010s\u2013now", "\u201CNet worth\u201D pages, viral posts, AI-generated encyclopedia entries. A state account puts $8bn in front of millions at zero cost.", "Revenue, engagement, and a permanent answer to anyone who says Palestinians in Gaza need food.")],
            src="Analysis. Attributions are to the reporting cited in this article."),
        4: dict(
            n="Figure 4", kicker="THE ASYMMETRY",
            title="Who held the money. Who holds the blame.",
            sub="Both columns are drawn from the same body of reporting \u2014 including the most hostile.",
            p=[("Yasser Arafat", "doc", "Control of funds",
                ["IMF: $900m in revenue routed to an account under his personal control, 1995\u20132000",
                 "Forensic audit: a secret portfolio worth close to $1bn",
                 "Sole signatory over monopolies on cement, fuel and cigarettes"],
                "How he is remembered",
                ["Ascetic. Frugal. Lived in a shelled compound.",
                 "A former head of the Palestinian National Fund: no house, no orchard, no personal account.",
                 "His accusers volunteered his personal austerity."]),
               ("Suha Arafat", "no", "Control of funds",
                ["No budget authority. No signing power. No office.",
                 "Never charged, anywhere, with taking Palestinian public funds.",
                 "No bank record has ever been produced."],
                "How she is remembered",
                ["The shopping. The hotel. The fashion shows.",
                 "Her uncovered hair. Her Western clothes.",
                 "A neighbour\u2019s verdict, printed in a US daily: Paris and money do that to a person."])],
            punch="The money went where the control was. The blame went where the woman was.",
            src="Sources: IMF September 2003; forensic audit commissioned by the PA finance ministry; contemporaneous US and Israeli reporting."),
        5: dict(
            n="Figure 5", kicker="ANATOMY OF A CLAIM",
            title="Four assertions about a private citizen",
            sub="Posted January 2025 by the official account of the State of Israel, concerning Zahwa Arafat \u2014 born 1995, no public office, never charged with anything, anywhere.",
            rows=[("01", "She is worth $8 billion", "No filing, registry entry, audit, court record or named source has ever been produced.", "Unevidenced", 0),
                  ("02", "She owns prime real estate across London", "No title record, company filing or address has ever been produced.", "Unevidenced", 0),
                  ("03", "She lives in Paris", "She has lived in Malta since childhood. Wire photographs filed from her family\u2019s Malta home in 2011 and 2012; family interviews from 2009 to 2025; a degree from a Maltese university.", "False \u2014 and checkable", 1),
                  ("04", "She is eligible for UNRWA funds as a refugee", "No evidence has been offered that she has ever registered with, applied to, or received anything from UNRWA.", "Unevidenced", 0)],
            punch="If the easiest verifiable detail in a four-sentence claim is wrong, ask what standard of care was applied to the other three.",
            post=dict(name="Israel \u05d9\u05e9\u05e8\u05d0\u05dc", handle="@Israel",
                      date="13 January 2025",
                      text="Billionaire, real estate owner, and eligible for UNRWA funds: Zahwa Arafat, the daughter of Yasser Arafat, is worth $8 billion, thanks to the \u201cPalestinian aid\u201d she inherited from her father. She owns prime real estate across London, lives in Paris, yet, according to UNRWA\u2019s standards, she is considered a refugee and eligible to receive funds. This is how UNRWA operates.",
                      url="https://x.com/Israel/status/1878773406188868046",
                      linklabel="View the original post on X",
                      note="Reproduced verbatim as the exhibit under examination."),
            src="The post remains publicly visible. No correction has been issued."),
    },
    "ar": {
        1: dict(
            n="\u0627\u0644\u0634\u0643\u0644 \u0661", kicker="\u062F\u0641\u062A\u0631 \u0627\u0644\u0623\u0631\u0642\u0627\u0645",
            title="\u0645\u0627 \u0642\u064A\u0644 \u0625\u0646\u0651 \u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A \u062A\u062A\u0642\u0627\u0636\u0627\u0647",
            sub="\u0645\u0628\u0627\u0644\u063A \u0634\u0647\u0631\u064A\u0629 \u0645\u0632\u0639\u0648\u0645\u0629 \u062A\u062F\u0627\u0648\u0644\u062A\u0647\u0627 \u0627\u0644\u0635\u062D\u0627\u0641\u0629 \u0628\u064A\u0646 \u0662\u0660\u0660\u0663 \u0648\u0662\u0660\u0662\u0660. \u0627\u0644\u0634\u062E\u0635 \u0646\u0641\u0633\u0647\u060C \u0648\u0627\u0644\u0641\u062A\u0631\u0629 \u0646\u0641\u0633\u0647\u0627\u060C \u0648\u0627\u0644\u0639\u0645\u0644\u0629 \u0646\u0641\u0633\u0647\u0627.",
            head=["\u0627\u0644\u0645\u0628\u0644\u063A \u0627\u0644\u0645\u0632\u0639\u0648\u0645 \u0634\u0647\u0631\u064A\u0627\u064B", "\u0645\u0646 \u0642\u0627\u0644\u0647", "\u0627\u0644\u062F\u0644\u064A\u0644 \u0627\u0644\u0645\u0642\u062F\u0651\u064E\u0645"],
            rows=[("\u0662\u0660\u0660 \u0623\u0644\u0641 $", 100, "\u0645\u062C\u0644\u0629 \u0623\u0645\u064A\u0631\u0643\u064A\u0629\u060C \u062A\u0634\u0631\u064A\u0646 \u0627\u0644\u062B\u0627\u0646\u064A \u0662\u0660\u0660\u0664 \u2014 \u00AB\u0645\u0637\u0644\u0639\u0648\u0646 \u0639\u0644\u0649 \u0645\u0627\u0644\u064A\u0629 \u0639\u0631\u0641\u0627\u062A\u00BB", 0, "\u0644\u0627 \u0645\u0635\u062F\u0631 \u0645\u0639\u0644\u0646"),
                  ("\u0661\u0660\u0660 \u0623\u0644\u0641 $", 50, "\u062A\u0644\u0641\u0632\u064A\u0648\u0646 \u0623\u0645\u064A\u0631\u0643\u064A\u060C \u0662\u0660\u0660\u0663 \u2014 \u0645\u0633\u0624\u0648\u0644\u0648\u0646 \u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0648\u0646\u060C \u062B\u0645\u0651 \u0645\u0633\u0624\u0648\u0644 \u0641\u0644\u0633\u0637\u064A\u0646\u064A \u0644\u0645 \u064A\u064F\u0633\u0645\u0651", 0, "\u0644\u0627 \u0645\u0635\u062F\u0631 \u0645\u0639\u0644\u0646"),
                  ("\u0665\u0660 \u0623\u0644\u0641 $", 25, "\u0635\u062D\u0627\u0641\u0629 \u0639\u0631\u0628\u064A\u0629\u060C \u0662\u0660\u0661\u0661 \u2014 \u062F\u0648\u0646 \u0625\u0633\u0646\u0627\u062F\u061B \u0648\u0642\u062F \u0646\u0641\u062A\u0647 \u062A\u062D\u062F\u064A\u062F\u0627\u064B", 0, "\u0644\u0627 \u0645\u0635\u062F\u0631 \u0645\u0639\u0644\u0646"),
                  ("\u0661\u0662 \u0623\u0644\u0641 $", 6, "\u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A\u060C \u0627\u0644\u0634\u0631\u0642 \u0627\u0644\u0623\u0648\u0633\u0637 \u0662\u0660\u0661\u0661 \u2014 \u0648\u0635\u0641\u062A\u0647 \u0628\u0645\u0639\u0627\u0634 \u0645\u0646\u0638\u0645\u0629 \u0627\u0644\u062A\u062D\u0631\u064A\u0631\u060C \u0632\u0627\u0626\u062F \u0627\u0644\u0625\u064A\u062C\u0627\u0631", 1, "\u0645\u0635\u062F\u0631 \u0645\u0633\u0645\u0651\u0649 \u0648\u0645\u0648\u062B\u0651\u064E\u0642"),
                  ("\u0661\u0660 \u0622\u0644\u0627\u0641 \u20AC", 6, "\u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A\u060C \u0642\u0646\u0627\u0629 \u0643\u0627\u0646 \u0627\u0644\u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0629 \u0662\u0660\u0662\u0660 \u2014 \u0627\u0644\u0631\u0648\u0627\u064A\u0629 \u0646\u0641\u0633\u0647\u0627 \u0628\u0639\u062F \u062A\u0633\u0639 \u0633\u0646\u0648\u0627\u062A", 1, "\u0645\u0635\u062F\u0631 \u0645\u0633\u0645\u0651\u0649 \u0648\u0645\u0648\u062B\u0651\u064E\u0642")],
            punch="\u0641\u0627\u0631\u0642 \u0633\u062A\u0629 \u0639\u0634\u0631 \u0636\u0639\u0641\u0627\u064B. \u0645\u0646 \u0627\u0644\u0645\u0633\u062A\u062D\u064A\u0644 \u0623\u0646 \u062A\u0643\u0648\u0646 \u0643\u0644\u0651\u0647\u0627 \u0635\u062D\u064A\u062D\u0629.",
            note="\u0648\u0645\u0646\u0641\u0635\u0644\u0627\u064B\u060C \u064A\u062A\u062F\u0627\u0648\u0644 \u0645\u0646\u0630 \u0662\u0660\u0660\u0664 \u0631\u0642\u0645 \u0662\u0662 \u0645\u0644\u064A\u0648\u0646 \u062F\u0648\u0644\u0627\u0631 \u0633\u0646\u0648\u064A\u0627\u064B \u2014 \u062A\u0633\u0648\u064A\u0629 \u0645\u0632\u0639\u0648\u0645\u0629 \u062A\u064F\u062F\u0641\u0639 \u0645\u0646 \u062D\u0633\u0627\u0628\u0627\u062A \u0633\u0631\u064A\u0629 \u2014 \u0645\u0646\u0633\u0648\u0628\u0627\u064B \u0625\u0644\u0649 \u0645\u0633\u0624\u0648\u0644\u064A\u0646 \u0641\u0644\u0633\u0637\u064A\u0646\u064A\u064A\u0646 \u0644\u0645 \u064A\u064F\u0633\u0645\u0651\u0648\u0627. \u0648\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u064E\u0645 \u0646\u0635\u0651 \u0627\u0644\u0627\u062A\u0641\u0627\u0642 \u0642\u0637\u0651.",
            src="\u062C\u064F\u0645\u0639\u062A \u0645\u0646 \u062A\u0642\u0627\u0631\u064A\u0631 \u0627\u0644\u0648\u0643\u0627\u0644\u0627\u062A \u0648\u0627\u0644\u0628\u062B \u0627\u0644\u0645\u0639\u0627\u0635\u0631\u0629\u060C \u0662\u0660\u0660\u0663\u2013\u0662\u0660\u0662\u0660."),
        2: dict(
            n="\u0627\u0644\u0634\u0643\u0644 \u0662", kicker="\u0627\u0644\u0627\u062F\u0651\u0639\u0627\u0621 \u0641\u064A \u0645\u0648\u0627\u062C\u0647\u0629 \u0627\u0644\u0633\u062C\u0644",
            title="\u0645\u0627 \u0623\u064F\u0639\u0644\u0646\u060C \u0648\u0645\u0627 \u062B\u064E\u0628\u064E\u062A \u0641\u0639\u0644\u0627\u064B",
            sub="\u0633\u062A\u0629 \u0627\u062F\u0651\u0639\u0627\u0621\u0627\u062A \u0635\u0627\u063A\u062A \u0627\u0644\u0630\u0627\u0643\u0631\u0629 \u0627\u0644\u0639\u0627\u0645\u0629 \u0639\u0646 \u0645\u0627\u0644\u064A\u0629 \u0639\u0627\u0626\u0644\u0629 \u0639\u0631\u0641\u0627\u062A.",
            head=["\u0643\u0645\u0627 \u062A\u064E\u062F\u0627\u0648\u064E\u0644", "\u0645\u0627 \u064A\u064F\u0638\u0647\u0631\u0647 \u0627\u0644\u0633\u062C\u0644"],
            rows=[("\u062E\u0636\u0639\u062A \u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A \u0644\u062A\u062D\u0642\u064A\u0642 \u0641\u064A \u063A\u0633\u064A\u0644 \u0627\u0644\u0623\u0645\u0648\u0627\u0644 \u0641\u064A \u0641\u0631\u0646\u0633\u0627", "\u062A\u062D\u0642\u064A\u0642 \u0623\u0648\u0651\u0644\u064A \u0641\u064F\u062A\u062D \u0641\u064A \u062A\u0634\u0631\u064A\u0646 \u0627\u0644\u0623\u0648\u0644 \u0662\u0660\u0660\u0663. \u0648\u0642\u0627\u0644 \u0645\u0633\u0624\u0648\u0644\u0648\u0646 \u0641\u0631\u0646\u0633\u064A\u0648\u0646 \u0625\u0646\u0651 \u0634\u0631\u0637 \u0627\u0644\u0645\u0635\u062F\u0631 \u063A\u064A\u0631 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0644\u0645 \u064A\u062A\u062D\u0642\u0651\u0642. \u0644\u0627 \u062A\u062D\u0642\u064A\u0642 \u0631\u0633\u0645\u064A\u060C \u0648\u0644\u0627 \u062A\u0647\u0645\u0629\u060C \u0648\u0644\u0627 \u0642\u0631\u0627\u0631 \u0645\u0639\u0644\u0646 \u2014 \u0623\u0628\u062F\u0627\u064B.", 0),
                  ("\u0623\u0642\u0627\u0645\u062A \u0641\u064A \u0637\u0627\u0628\u0642 \u0643\u0627\u0645\u0644 \u0628\u0641\u0646\u062F\u0642 \u0628\u0627\u0631\u064A\u0633\u064A \u062E\u0645\u0633 \u0646\u062C\u0648\u0645", "\u0623\u0641\u0627\u062F \u0627\u0644\u0641\u0646\u062F\u0642 \u0628\u0623\u0646\u0651\u0647\u0627 \u0644\u0645 \u062A\u0646\u0632\u0644 \u0641\u064A\u0647 \u0642\u0637\u0651. \u0648\u0646\u064F\u0634\u0631 \u0627\u0644\u0646\u0641\u064A. \u0648\u0627\u0633\u062A\u0645\u0631\u0651 \u0627\u0644\u0627\u062F\u0651\u0639\u0627\u0621 \u064A\u064F\u062A\u062F\u0627\u0648\u0644 \u062F\u0648\u0646 \u062A\u063A\u064A\u064A\u0631.", 0),
                  ("\u062A\u0644\u0642\u0651\u062A \u0661\u0660\u0660 \u0623\u0644\u0641 \u062F\u0648\u0644\u0627\u0631 \u0634\u0647\u0631\u064A\u0627\u064B \u0645\u0646 \u0627\u0644\u0645\u0627\u0644 \u0627\u0644\u0641\u0644\u0633\u0637\u064A\u0646\u064A", "\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u0645 \u0637\u0648\u0627\u0644 \u0627\u062B\u0646\u062A\u064A\u0646 \u0648\u0639\u0634\u0631\u064A\u0646 \u0633\u0646\u0629 \u0623\u064A\u0651 \u0643\u0634\u0641 \u0645\u0635\u0631\u0641\u064A \u0623\u0648 \u0623\u0645\u0631 \u062A\u062D\u0648\u064A\u0644 \u0623\u0648 \u0628\u0646\u062F \u0645\u0648\u0627\u0632\u0646\u0629 \u0623\u0648 \u0645\u0635\u062F\u0631 \u0645\u0633\u0645\u0651\u0649.", 0),
                  ("\u0632\u0647\u0648\u0629 \u0639\u0631\u0641\u0627\u062A \u062A\u0645\u0644\u0643 \u0668 \u0645\u0644\u064A\u0627\u0631\u0627\u062A \u0648\u0639\u0642\u0627\u0631\u0627\u062A \u0641\u064A \u0644\u0646\u062F\u0646", "\u0644\u0627 \u0648\u062B\u064A\u0642\u0629 \u0648\u0644\u0627 \u0642\u064A\u062F \u0633\u062C\u0644\u0651 \u0648\u0644\u0627 \u062A\u062F\u0642\u064A\u0642 \u0648\u0644\u0627 \u062D\u0643\u0645 \u0642\u0636\u0627\u0626\u064A. \u0648\u0627\u0644\u0645\u0646\u0634\u0648\u0631 \u0646\u0641\u0633\u0647 \u064A\u0636\u0639\u0647\u0627 \u0641\u064A \u0628\u0627\u0631\u064A\u0633\u061B \u0648\u0647\u064A \u062A\u0642\u064A\u0645 \u0641\u064A \u0645\u0627\u0644\u0637\u0627 \u0645\u0646\u0630 \u0637\u0641\u0648\u0644\u062A\u0647\u0627.", 0),
                  ("\u0635\u062F\u0631\u062A \u0628\u062D\u0642\u0651\u0647\u0627 \u0645\u0630\u0643\u0631\u0629 \u062A\u0648\u0642\u064A\u0641 \u062A\u0648\u0646\u0633\u064A\u0629", "\u0635\u062D\u064A\u062D. \u0635\u062F\u0631\u062A \u0641\u064A \u062A\u0634\u0631\u064A\u0646 \u0627\u0644\u0623\u0648\u0644 \u0662\u0660\u0661\u0661 \u0628\u0634\u0623\u0646 \u0645\u0634\u0631\u0648\u0639 \u0645\u062F\u0631\u0633\u0629 \u062E\u0627\u0635\u0629 \u0645\u0639 \u0645\u062D\u064A\u0637 \u0639\u0627\u0626\u0644\u0629 \u0628\u0646 \u0639\u0644\u064A \u2014 \u0645\u0633\u0623\u0644\u0629 \u062A\u062C\u0627\u0631\u064A\u0629 \u062A\u0648\u0646\u0633\u064A\u0629\u060C \u0644\u0627 \u0645\u0627\u0644\u0627\u064B \u0639\u0627\u0645\u0651\u0627\u064B \u0641\u0644\u0633\u0637\u064A\u0646\u064A\u0627\u064B.", 1),
                  ("\u062A\u062D\u0648\u064A\u0644 \u0669\u0660\u0660 \u0645\u0644\u064A\u0648\u0646 \u062F\u0648\u0644\u0627\u0631 \u0645\u0646 \u0627\u0644\u0625\u064A\u0631\u0627\u062F\u0627\u062A\u060C \u0661\u0669\u0669\u0665\u2013\u0662\u0660\u0660\u0660", "\u0635\u062D\u064A\u062D\u060C \u0648\u0641\u0642 \u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0646\u0642\u062F \u0627\u0644\u062F\u0648\u0644\u064A. \u0625\u0644\u0649 \u062D\u0633\u0627\u0628 \u064A\u0633\u064A\u0637\u0631 \u0639\u0644\u064A\u0647 \u064A\u0627\u0633\u0631 \u0639\u0631\u0641\u0627\u062A. \u0648\u0627\u0633\u062A\u064F\u0631\u062F\u0651 \u0645\u0639\u0638\u0645 \u0627\u0644\u062C\u0632\u0621 \u0627\u0644\u0645\u062A\u062A\u0628\u0651\u0639 \u0641\u064A \u0625\u0635\u0644\u0627\u062D\u0627\u062A \u0633\u0644\u0627\u0645 \u0641\u064A\u0627\u0636.", 1)],
            key=["\u0628\u0644\u0627 \u062F\u0644\u064A\u0644 \u0623\u0648 \u0645\u0646\u0627\u0642\u0636 \u0644\u0644\u0648\u0642\u0627\u0626\u0639", "\u0645\u0648\u062B\u0651\u064E\u0642"],
            src="\u0627\u0644\u0645\u0635\u0627\u062F\u0631: \u0628\u064A\u0627\u0646\u0627\u062A \u0627\u0644\u0646\u064A\u0627\u0628\u0629 \u0627\u0644\u0628\u0627\u0631\u064A\u0633\u064A\u0629 \u0662\u0660\u0660\u0663\u2013\u0662\u0660\u0660\u0664\u061B \u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0646\u0642\u062F \u0627\u0644\u062F\u0648\u0644\u064A \u0662\u0660\u0660\u0663\u061B \u0648\u0632\u0627\u0631\u0629 \u0627\u0644\u0639\u062F\u0644 \u0627\u0644\u062A\u0648\u0646\u0633\u064A\u0629 \u0662\u0660\u0661\u0661."),
        3: dict(
            n="\u0627\u0644\u0634\u0643\u0644 \u0663", kicker="\u0633\u0648\u0642 \u0627\u0644\u0631\u0648\u0627\u064A\u0629",
            title="\u0623\u0631\u0628\u0639\u0629 \u0645\u0634\u062A\u0631\u064A\u0646\u060C \u0648\u0645\u0627 \u062D\u0635\u0644 \u0639\u0644\u064A\u0647 \u0643\u0644\u0651 \u0645\u0646\u0647\u0645",
            sub="\u0627\u0644\u062A\u0634\u0647\u064A\u0631 \u0644\u064A\u0633 \u062E\u0637\u0623\u064B\u060C \u0628\u0644 \u0645\u0646\u062A\u064E\u062C\u061B \u0648\u0644\u0644\u0645\u0646\u062A\u064E\u062C \u0645\u0634\u062A\u0631\u0648\u0646.",
            l1="\u0645\u0627 \u0623\u064F\u062F\u062E\u0650\u0644 \u0625\u0644\u0649 \u0627\u0644\u062A\u062F\u0627\u0648\u0644", l2="\u0645\u0627 \u0627\u0634\u062A\u0631\u0627\u0647 \u0644\u0647\u0645",
            cols=[("\u0627\u0644\u062D\u0643\u0648\u0645\u0629 \u0627\u0644\u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0629", "\u0662\u0660\u0660\u0662\u2013\u0662\u0660\u0660\u0664", "\u0627\u0644\u0627\u0633\u062A\u062E\u0628\u0627\u0631\u0627\u062A \u0627\u0644\u0639\u0633\u0643\u0631\u064A\u0629 \u062A\u064F\u0628\u0644\u0650\u063A \u0627\u0644\u0643\u0646\u064A\u0633\u062A \u0623\u0646\u0651 \u0639\u0631\u0641\u0627\u062A \u064A\u0633\u064A\u0637\u0631 \u0639\u0644\u0649 \u0661\u066B\u0663 \u0645\u0644\u064A\u0627\u0631. \u0648\u0645\u0633\u0624\u0648\u0644\u0648\u0646 \u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0648\u0646 \u0647\u0645 \u0645\u0635\u062F\u0631 \u0631\u0642\u0645 \u0627\u0644\u0645\u0626\u0629 \u0623\u0644\u0641 \u0634\u0647\u0631\u064A\u0627\u064B.", "\u064A\u062D\u0648\u0651\u0644 \u0642\u064A\u0627\u062F\u0629 \u0648\u0637\u0646\u064A\u0629 \u0625\u0644\u0649 \u0639\u0635\u0627\u0628\u0629. \u0648\u0645\u062A\u0649 \u0635\u0627\u0631\u062A \u0627\u0644\u062D\u0631\u0643\u0629 \u0639\u0635\u0627\u0628\u0629\u060C \u064A\u0633\u0642\u0637 \u0627\u0644\u0633\u0624\u0627\u0644 \u0639\u0645\u0651\u0627 \u062A\u0633\u062A\u062D\u0642\u0651\u0647 \u0633\u064A\u0627\u0633\u064A\u0627\u064B."),
                  ("\u0627\u0644\u062D\u0631\u0633 \u0627\u0644\u0642\u062F\u064A\u0645 \u0641\u064A \u0627\u0644\u0633\u0644\u0637\u0629 \u0648\u0641\u062A\u062D", "\u0662\u0660\u0660\u0664\u2013\u0627\u0644\u064A\u0648\u0645", "\u0623\u0636\u062E\u0645 \u0627\u0644\u0623\u0631\u0642\u0627\u0645 \u0648\u0623\u0642\u0644\u0651\u0647\u0627 \u0625\u0633\u0646\u0627\u062F\u0627\u064B \u2014 \u0662\u0662 \u0645\u0644\u064A\u0648\u0646\u0627\u064B \u0633\u0646\u0648\u064A\u0627\u064B\u060C \u00AB\u0645\u0626\u0627\u062A \u0627\u0644\u0645\u0644\u0627\u064A\u064A\u0646 \u0645\u0648\u0631\u0648\u062B\u0629\u00BB \u2014 \u062A\u064F\u0646\u0633\u064E\u0628 \u0625\u0644\u0649 \u0645\u0633\u0624\u0648\u0644\u064A\u0646 \u0641\u0644\u0633\u0637\u064A\u0646\u064A\u064A\u0646 \u0644\u0627 \u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u064A\u0646.", "\u064A\u064F\u062D\u064E\u064A\u0651\u062F \u0623\u0631\u0645\u0644\u0629 \u0627\u0646\u062A\u0642\u062F\u062A \u0641\u0633\u0627\u062F \u0627\u0644\u0633\u0644\u0637\u0629 \u0639\u0644\u0646\u0627\u064B\u060C \u0648\u062A\u062D\u0643\u0651\u0645\u062A \u0628\u0627\u0644\u0648\u0635\u0648\u0644 \u0625\u0644\u0649 \u0627\u0644\u0631\u0626\u064A\u0633 \u0627\u0644\u0645\u062D\u062A\u0636\u0631\u060C \u0648\u062A\u0639\u0631\u0641 \u0645\u0648\u0627\u0642\u0639 \u0627\u0644\u062D\u0633\u0627\u0628\u0627\u062A."),
                  ("\u062A\u0648\u0646\u0633 \u0628\u0646 \u0639\u0644\u064A", "\u0662\u0660\u0660\u0667\u2013\u0662\u0660\u0661\u0661", "\u062A\u064F\u062C\u0631\u0651\u062F\u0647\u0627 \u0645\u0646 \u0627\u0644\u062C\u0646\u0633\u064A\u0629 \u0628\u0645\u0631\u0633\u0648\u0645 \u0628\u0639\u062F \u0627\u0646\u062A\u0642\u0627\u062F\u0647\u0627 \u0627\u0644\u0639\u0627\u0626\u0644\u0629 \u0627\u0644\u062D\u0627\u0643\u0645\u0629 \u0623\u0645\u0627\u0645 \u0627\u0644\u0633\u0641\u064A\u0631 \u0627\u0644\u0623\u0645\u064A\u0631\u0643\u064A\u060C \u062B\u0645\u0651 \u064A\u0644\u062D\u0642 \u0627\u0633\u0645\u0647\u0627 \u0628\u062D\u0645\u0644\u0629 \u0645\u0627 \u0628\u0639\u062F \u0627\u0644\u062B\u0648\u0631\u0629.", "\u064A\u062A\u062E\u0644\u0651\u0635 \u0645\u0646 \u0636\u064A\u0641\u0629 \u0645\u0632\u0639\u062C\u0629\u060C \u062B\u0645\u0651 \u064A\u0645\u0646\u062D \u0627\u0644\u0639\u0627\u0644\u0645 \u0648\u062B\u064A\u0642\u0629 \u0642\u0636\u0627\u0626\u064A\u0629 \u062A\u0628\u062F\u0648 \u0644\u0644\u0648\u0647\u0644\u0629 \u0627\u0644\u0623\u0648\u0644\u0649 \u062F\u0644\u064A\u0644\u0627\u064B \u0639\u0644\u0649 \u0643\u0644\u0651 \u0645\u0627 \u0639\u062F\u0627\u0647."),
                  ("\u0627\u0642\u062A\u0635\u0627\u062F \u0627\u0644\u0645\u062D\u062A\u0648\u0649", "\u0645\u0646 \u0662\u0660\u0661\u0660 \u062D\u062A\u0651\u0649 \u0627\u0644\u064A\u0648\u0645", "\u0635\u0641\u062D\u0627\u062A \u00AB\u0627\u0644\u062B\u0631\u0648\u0629 \u0627\u0644\u0635\u0627\u0641\u064A\u0629\u00BB\u060C \u0645\u0646\u0634\u0648\u0631\u0627\u062A \u0641\u064A\u0631\u0648\u0633\u064A\u0629\u060C \u0645\u0648\u0633\u0648\u0639\u0627\u062A \u062A\u0648\u0644\u0651\u062F\u0647\u0627 \u0627\u0644\u0622\u0644\u0629. \u062D\u0633\u0627\u0628 \u0631\u0633\u0645\u064A \u064A\u0636\u0639 \u0668 \u0645\u0644\u064A\u0627\u0631\u0627\u062A \u0623\u0645\u0627\u0645 \u0627\u0644\u0645\u0644\u0627\u064A\u064A\u0646 \u0628\u0644\u0627 \u0643\u0644\u0641\u0629.", "\u0625\u064A\u0631\u0627\u062F\u0627\u062A \u0648\u062A\u0641\u0627\u0639\u0644\u060C \u0648\u0631\u062F\u0651 \u062F\u0627\u0626\u0645 \u062C\u0627\u0647\u0632 \u0639\u0644\u0649 \u0643\u0644\u0651 \u0645\u0646 \u064A\u0642\u0648\u0644 \u0625\u0646\u0651 \u0641\u0644\u0633\u0637\u064A\u0646\u064A\u064A \u063A\u0632\u0629 \u0628\u062D\u0627\u062C\u0629 \u0625\u0644\u0649 \u0637\u0639\u0627\u0645.")],
            src="\u062A\u062D\u0644\u064A\u0644. \u0627\u0644\u0625\u0633\u0646\u0627\u062F\u0627\u062A \u0648\u0641\u0642 \u0627\u0644\u062A\u0642\u0627\u0631\u064A\u0631 \u0627\u0644\u0645\u0630\u0643\u0648\u0631\u0629 \u0641\u064A \u0627\u0644\u0645\u0642\u0627\u0644."),
        4: dict(
            n="\u0627\u0644\u0634\u0643\u0644 \u0664", kicker="\u0627\u0644\u0627\u062E\u062A\u0644\u0627\u0644",
            title="\u0645\u064E\u0646 \u0623\u0645\u0633\u0643 \u0627\u0644\u0645\u0627\u0644\u061F \u0648\u0645\u064E\u0646 \u064A\u062D\u0645\u0644 \u0627\u0644\u062A\u0647\u0645\u0629\u061F",
            sub="\u0627\u0644\u0639\u0645\u0648\u062F\u0627\u0646 \u0645\u0633\u062A\u0645\u062F\u0651\u0627\u0646 \u0645\u0646 \u0627\u0644\u0645\u0627\u062F\u0629 \u0627\u0644\u0635\u062D\u0641\u064A\u0629 \u0646\u0641\u0633\u0647\u0627 \u2014 \u0628\u0645\u0627 \u0641\u064A\u0647\u0627 \u0623\u0634\u062F\u0651\u0647\u0627 \u0639\u062F\u0627\u0621\u064B.",
            p=[("\u064A\u0627\u0633\u0631 \u0639\u0631\u0641\u0627\u062A", "doc", "\u0627\u0644\u0633\u064A\u0637\u0631\u0629 \u0639\u0644\u0649 \u0627\u0644\u0645\u0627\u0644",
                ["\u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0646\u0642\u062F: \u0669\u0660\u0660 \u0645\u0644\u064A\u0648\u0646 \u062F\u0648\u0644\u0627\u0631 \u0625\u0644\u0649 \u062D\u0633\u0627\u0628 \u062A\u062D\u062A \u0633\u064A\u0637\u0631\u062A\u0647 \u0627\u0644\u0634\u062E\u0635\u064A\u0629\u060C \u0661\u0669\u0669\u0665\u2013\u0662\u0660\u0660\u0660",
                 "\u062A\u062F\u0642\u064A\u0642 \u062C\u0646\u0627\u0626\u064A: \u0645\u062D\u0641\u0638\u0629 \u0627\u0633\u062A\u062B\u0645\u0627\u0631\u064A\u0629 \u0633\u0631\u064A\u0629 \u062A\u0642\u0627\u0631\u0628 \u0627\u0644\u0645\u0644\u064A\u0627\u0631",
                 "\u0627\u0644\u0645\u0648\u0642\u0651\u0650\u0639 \u0627\u0644\u0648\u062D\u064A\u062F \u0639\u0644\u0649 \u0627\u062D\u062A\u0643\u0627\u0631\u0627\u062A \u0627\u0644\u0625\u0633\u0645\u0646\u062A \u0648\u0627\u0644\u0648\u0642\u0648\u062F \u0648\u0627\u0644\u062A\u0628\u063A"],
                "\u0643\u064A\u0641 \u064A\u064F\u0630\u0643\u064E\u0631",
                ["\u0632\u0627\u0647\u062F. \u0645\u0642\u062A\u0635\u062F. \u0639\u0627\u0634 \u0641\u064A \u0645\u0642\u0631\u0651 \u0645\u0642\u0635\u0648\u0641.",
                 "\u0631\u0626\u064A\u0633 \u0633\u0627\u0628\u0642 \u0644\u0644\u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0642\u0648\u0645\u064A: \u0644\u0627 \u0628\u064A\u062A \u0648\u0644\u0627 \u0628\u0633\u062A\u0627\u0646 \u0648\u0644\u0627 \u062D\u0633\u0627\u0628 \u0634\u062E\u0635\u064A.",
                 "\u0648\u0645\u062A\u0651\u0647\u0645\u0648\u0647 \u0623\u0646\u0641\u0633\u0647\u0645 \u0634\u0647\u062F\u0648\u0627 \u0628\u062A\u0642\u0634\u0651\u0641\u0647."]),
               ("\u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062A", "no", "\u0627\u0644\u0633\u064A\u0637\u0631\u0629 \u0639\u0644\u0649 \u0627\u0644\u0645\u0627\u0644",
                ["\u0644\u0627 \u0635\u0644\u0627\u062D\u064A\u0629 \u0645\u0627\u0644\u064A\u0629. \u0644\u0627 \u062D\u0642\u0651 \u062A\u0648\u0642\u064A\u0639. \u0644\u0627 \u0645\u0646\u0635\u0628.",
                 "\u0644\u0645 \u062A\u064F\u062A\u0651\u0647\u0645 \u0642\u0637\u0651\u060C \u0641\u064A \u0623\u064A\u0651 \u0645\u0643\u0627\u0646\u060C \u0628\u0623\u062E\u0630 \u0645\u0627\u0644 \u0639\u0627\u0645\u0651 \u0641\u0644\u0633\u0637\u064A\u0646\u064A.",
                 "\u0648\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u064E\u0645 \u0623\u064A\u0651 \u0643\u0634\u0641 \u0645\u0635\u0631\u0641\u064A \u0642\u0637\u0651."],
                "\u0643\u064A\u0641 \u062A\u064F\u0630\u0643\u064E\u0631",
                ["\u0627\u0644\u062A\u0633\u0648\u0651\u0642. \u0627\u0644\u0641\u0646\u062F\u0642. \u0639\u0631\u0648\u0636 \u0627\u0644\u0623\u0632\u064A\u0627\u0621.",
                 "\u0634\u0639\u0631\u0647\u0627 \u0627\u0644\u0645\u0643\u0634\u0648\u0641. \u0645\u0644\u0627\u0628\u0633\u0647\u0627 \u0627\u0644\u063A\u0631\u0628\u064A\u0629.",
                 "\u062D\u0643\u0645 \u062C\u0627\u0631\u0629\u060C \u0646\u064F\u0634\u0631 \u0641\u064A \u0635\u062D\u064A\u0641\u0629 \u0623\u0645\u064A\u0631\u0643\u064A\u0629: \u0628\u0627\u0631\u064A\u0633 \u0648\u0627\u0644\u0645\u0627\u0644 \u064A\u0641\u0639\u0644\u0627\u0646 \u0630\u0644\u0643 \u0628\u0627\u0644\u0645\u0631\u0621."])],
            punch="\u0630\u0647\u0628 \u0627\u0644\u0645\u0627\u0644 \u062D\u064A\u062B \u0643\u0627\u0646\u062A \u0627\u0644\u0633\u064A\u0637\u0631\u0629. \u0648\u0630\u0647\u0628\u062A \u0627\u0644\u062A\u0647\u0645\u0629 \u062D\u064A\u062B \u0643\u0627\u0646\u062A \u0627\u0644\u0645\u0631\u0623\u0629.",
            src="\u0627\u0644\u0645\u0635\u0627\u062F\u0631: \u0635\u0646\u062F\u0648\u0642 \u0627\u0644\u0646\u0642\u062F \u0627\u0644\u062F\u0648\u0644\u064A \u0662\u0660\u0660\u0663\u061B \u062A\u062F\u0642\u064A\u0642 \u0643\u0644\u0651\u0641\u062A\u0647 \u0648\u0632\u0627\u0631\u0629 \u0627\u0644\u0645\u0627\u0644\u064A\u0629 \u0627\u0644\u0641\u0644\u0633\u0637\u064A\u0646\u064A\u0629\u061B \u062A\u0642\u0627\u0631\u064A\u0631 \u0623\u0645\u064A\u0631\u0643\u064A\u0629 \u0648\u0625\u0633\u0631\u0627\u0626\u064A\u0644\u064A\u0629 \u0645\u0639\u0627\u0635\u0631\u0629."),
        5: dict(
            n="\u0627\u0644\u0634\u0643\u0644 \u0665", kicker="\u062A\u0634\u0631\u064A\u062D \u0627\u062F\u0651\u0639\u0627\u0621",
            title="\u0623\u0631\u0628\u0639 \u062F\u0639\u0627\u0648\u0649 \u0628\u062D\u0642\u0651 \u0645\u0648\u0627\u0637\u0646\u0629 \u062E\u0627\u0635\u0629",
            sub="\u0646\u064F\u0634\u0650\u0631\u062A \u0641\u064A \u0643\u0627\u0646\u0648\u0646 \u0627\u0644\u062B\u0627\u0646\u064A \u0662\u0660\u0662\u0665 \u0639\u0646 \u0627\u0644\u062D\u0633\u0627\u0628 \u0627\u0644\u0631\u0633\u0645\u064A \u0644\u062F\u0648\u0644\u0629 \u0625\u0633\u0631\u0627\u0626\u064A\u0644 \u0628\u0634\u0623\u0646 \u0632\u0647\u0648\u0629 \u0639\u0631\u0641\u0627\u062A \u2014 \u0645\u0648\u0627\u0644\u064A\u062F \u0661\u0669\u0669\u0665\u060C \u0628\u0644\u0627 \u0645\u0646\u0635\u0628 \u0639\u0627\u0645\u060C \u0648\u0644\u0645 \u062A\u064F\u062A\u0651\u0647\u0645 \u0628\u0634\u064A\u0621 \u0641\u064A \u0623\u064A\u0651 \u0645\u0643\u0627\u0646.",
            rows=[("\u0660\u0661", "\u062A\u0645\u0644\u0643 \u062B\u0645\u0627\u0646\u064A\u0629 \u0645\u0644\u064A\u0627\u0631\u0627\u062A \u062F\u0648\u0644\u0627\u0631", "\u0644\u0645 \u062A\u064F\u0642\u062F\u0651\u064E\u0645 \u0642\u0637\u0651 \u0623\u064A\u0651 \u0648\u062B\u064A\u0642\u0629 \u0623\u0648 \u0642\u064A\u062F \u0633\u062C\u0644\u0651 \u0623\u0648 \u062A\u062F\u0642\u064A\u0642 \u0623\u0648 \u062D\u0643\u0645 \u0642\u0636\u0627\u0626\u064A \u0623\u0648 \u0645\u0635\u062F\u0631 \u0645\u0633\u0645\u0651\u0649.", "\u0628\u0644\u0627 \u062F\u0644\u064A\u0644", 0),
                  ("\u0660\u0662", "\u062A\u0645\u0644\u0643 \u0639\u0642\u0627\u0631\u0627\u062A \u0631\u0627\u0642\u064A\u0629 \u0641\u064A \u0644\u0646\u062F\u0646", "\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u064E\u0645 \u0623\u064A\u0651 \u0633\u0646\u062F \u0645\u0644\u0643\u064A\u0629 \u0623\u0648 \u0633\u062C\u0644\u0651 \u0634\u0631\u0643\u0629 \u0623\u0648 \u0639\u0646\u0648\u0627\u0646.", "\u0628\u0644\u0627 \u062F\u0644\u064A\u0644", 0),
                  ("\u0660\u0663", "\u062A\u0639\u064A\u0634 \u0641\u064A \u0628\u0627\u0631\u064A\u0633", "\u0647\u064A \u062A\u0642\u064A\u0645 \u0641\u064A \u0645\u0627\u0644\u0637\u0627 \u0645\u0646\u0630 \u0637\u0641\u0648\u0644\u062A\u0647\u0627. \u0635\u0648\u0631 \u0648\u0643\u0627\u0644\u0627\u062A \u0645\u0646 \u0645\u0646\u0632\u0644 \u0627\u0644\u0639\u0627\u0626\u0644\u0629 \u0641\u064A \u0645\u0627\u0644\u0637\u0627 \u0662\u0660\u0661\u0661 \u0648\u0662\u0660\u0661\u0662\u061B \u0645\u0642\u0627\u0628\u0644\u0627\u062A \u0639\u0627\u0626\u0644\u064A\u0629 \u0645\u0646 \u0662\u0660\u0660\u0669 \u0625\u0644\u0649 \u0662\u0660\u0662\u0665\u061B \u0648\u0634\u0647\u0627\u062F\u0629 \u062C\u0627\u0645\u0639\u064A\u0629 \u0645\u0627\u0644\u0637\u064A\u0629.", "\u062E\u0627\u0637\u0626 \u2014 \u0648\u0642\u0627\u0628\u0644 \u0644\u0644\u062A\u062D\u0642\u0651\u0642", 1),
                  ("\u0660\u0664", "\u062A\u0633\u062A\u062D\u0642\u0651 \u0623\u0645\u0648\u0627\u0644 \u0627\u0644\u0623\u0648\u0646\u0631\u0648\u0627 \u0628\u0648\u0635\u0641\u0647\u0627 \u0644\u0627\u062C\u0626\u0629", "\u0644\u0645 \u064A\u064F\u0642\u062F\u0651\u064E\u0645 \u062F\u0644\u064A\u0644 \u0639\u0644\u0649 \u0623\u0646\u0651\u0647\u0627 \u0633\u062C\u0651\u0644\u062A \u0644\u062F\u0649 \u0627\u0644\u0623\u0648\u0646\u0631\u0648\u0627 \u0623\u0648 \u062A\u0642\u062F\u0651\u0645\u062A \u0625\u0644\u064A\u0647\u0627 \u0623\u0648 \u062A\u0644\u0642\u0651\u062A \u0645\u0646\u0647\u0627 \u0634\u064A\u0626\u0627\u064B.", "\u0628\u0644\u0627 \u062F\u0644\u064A\u0644", 0)],
            post=dict(name="Israel ישראל", handle="@Israel",
                      date="13 January 2025",
                      text='Billionaire, real estate owner, and eligible for UNRWA funds: Zahwa Arafat, the daughter of Yasser Arafat, is worth $8 billion, thanks to the “Palestinian aid” she inherited from her father. She owns prime real estate across London, lives in Paris, yet, according to UNRWA’s standards, she is considered a refugee and eligible to receive funds. This is how UNRWA operates.',
                      url="https://x.com/Israel/status/1878773406188868046",
                      linklabel="عرض المنشور الأصلي على منصة إكس",
                      note="نصّ المنشور مثبّت حرفياً بلغته الأصلية بوصفه الوثيقة موضع الفحص."),
            punch="\u0625\u0630\u0627 \u0643\u0627\u0646\u062A \u0623\u0633\u0647\u0644 \u062A\u0641\u0635\u064A\u0644\u0629 \u0642\u0627\u0628\u0644\u0629 \u0644\u0644\u062A\u062D\u0642\u0642 \u0641\u064A \u0627\u062F\u0651\u0639\u0627\u0621 \u0645\u0646 \u0623\u0631\u0628\u0639 \u062C\u0645\u0644 \u062E\u0627\u0637\u0626\u0629\u060C \u0641\u0627\u0633\u0623\u0644 \u0623\u064A\u0651 \u0639\u0646\u0627\u064A\u0629 \u0628\u064F\u0630\u0644\u062A \u0641\u064A \u0627\u0644\u062B\u0644\u0627\u062B \u0627\u0644\u0623\u062E\u0631\u0649.",
            src="\u0627\u0644\u0645\u0646\u0634\u0648\u0631 \u0645\u0627 \u0632\u0627\u0644 \u0645\u062A\u0627\u062D\u0627\u064B \u0644\u0644\u0639\u0644\u0646. \u0648\u0644\u0645 \u064A\u0635\u062F\u0631 \u0623\u064A\u0651 \u062A\u0635\u062D\u064A\u062D."),
    },
}

META = {
    "en": dict(lang="en", dir="ltr", masthead="TIMES OF PALESTINE",
               section="INVESTIGATION \u00B7 ACCOUNTABILITY",
               fignote="Figure", other="\u0627\u0644\u0639\u0631\u0628\u064A\u0629", otherhref="index-ar.html",
               desc="How an unsourced number about Suha and Zahwa Arafat became a fact everybody knows \u2014 and what it cost Palestinians."),
    "ar": dict(lang="ar", dir="rtl", masthead="\u062A\u0627\u064A\u0645\u0632 \u0623\u0648\u0641 \u0641\u0644\u0633\u0637\u064A\u0646",
               section="\u062A\u062D\u0642\u064A\u0642 \u00B7 \u0645\u0633\u0627\u0621\u0644\u0629",
               fignote="\u0634\u0643\u0644", other="English", otherhref="index-en.html",
               desc="\u0643\u064A\u0641 \u0635\u0627\u0631 \u0631\u0642\u0645\u064C \u0628\u0644\u0627 \u0645\u0635\u062F\u0631 \u0639\u0646 \u0633\u0647\u0649 \u0648\u0632\u0647\u0648\u0629 \u0639\u0631\u0641\u0627\u062A \u062D\u0642\u064A\u0642\u0629\u064B \u064A\u0639\u0631\u0641\u0647\u0627 \u0627\u0644\u062C\u0645\u064A\u0639."),
}


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def chip(text, ok):
    return '<span class="chip %s">%s</span>' % ("ok" if ok else "no", esc(text))


def fighead(d):
    return ('<header class="fig-h"><p class="fig-n">%s <span>%s</span></p>'
            '<h3>%s</h3><p class="fig-s">%s</p></header>'
            % (esc(d["n"]), esc(d["kicker"]), esc(d["title"]), esc(d["sub"])))


def figfoot(d):
    return '<p class="fig-src">%s</p>' % esc(d["src"])


def fig1(d):
    h = ['<figure class="fig f1">', fighead(d),
         '<div class="f1-head"><span>%s</span><span>%s</span><span>%s</span></div>' % tuple(esc(x) for x in d["head"])]
    for amt, pct, who, ok, verdict in d["rows"]:
        h.append('<div class="f1-row %s"><div class="f1-bar" style="--w:%d%%"><span class="f1-amt">%s</span></div>'
                 '<p class="f1-who">%s</p><div class="f1-v">%s</div></div>'
                 % ("ok" if ok else "no", pct, esc(amt), esc(who), chip(verdict, ok)))
    h.append('<p class="punch">%s</p>' % esc(d["punch"]))
    h.append('<aside class="note">%s</aside>' % esc(d["note"]))
    h.append(figfoot(d) + "</figure>")
    return "".join(h)


def fig2(d):
    h = ['<figure class="fig f2">', fighead(d),
         '<div class="f2-head"><span>%s</span><span>%s</span></div>' % tuple(esc(x) for x in d["head"])]
    for claim, rec, ok in d["rows"]:
        h.append('<div class="f2-row %s"><p class="f2-c">%s</p><p class="f2-r">%s</p></div>'
                 % ("ok" if ok else "no", esc(claim), esc(rec)))
    h.append('<div class="f2-key">%s %s</div>' % (chip(d["key"][0], 0), chip(d["key"][1], 1)))
    h.append(figfoot(d) + "</figure>")
    return "".join(h)


def fig3(d):
    h = ['<figure class="fig f3">', fighead(d), '<div class="f3-grid">']
    for who, when, put, got in d["cols"]:
        h.append('<div class="f3-col"><p class="f3-when">%s</p><h4>%s</h4>'
                 '<p class="lab">%s</p><p class="f3-t">%s</p>'
                 '<p class="lab lab-b">%s</p><p class="f3-t f3-b">%s</p></div>'
                 % (esc(when), esc(who), esc(d["l1"]), esc(put), esc(d["l2"]), esc(got)))
    h.append('</div>' + figfoot(d) + "</figure>")
    return "".join(h)


def fig4(d):
    h = ['<figure class="fig f4">', fighead(d), '<div class="f4-grid">']
    for name, kind, h1, a, h2, b in d["p"]:
        items = "".join('<li>%s</li>' % esc(i) for i in a)
        items2 = "".join('<li>%s</li>' % esc(i) for i in b)
        h.append('<div class="f4-p %s"><h4>%s</h4><p class="lab">%s</p><ul class="f4-a">%s</ul>'
                 '<p class="lab lab-b">%s</p><ul class="f4-b">%s</ul></div>'
                 % (kind, esc(name), esc(h1), items, esc(h2), items2))
    h.append('</div><p class="punch punch-bar">%s</p>' % esc(d["punch"]))
    h.append(figfoot(d) + "</figure>")
    return "".join(h)


def fig5(d):
    h = ['<figure class="fig f5">', fighead(d)]
    post = d.get("post")
    if post:
        h.append('<blockquote class="xpost" lang="en" dir="ltr">')
        h.append('<p class="xpost-meta"><span class="xpost-name">%s</span> %s \u00b7 %s</p>'
                 % (esc(post["name"]), esc(post["handle"]), esc(post["date"])))
        h.append('<p class="xpost-text">%s</p>' % esc(post["text"]))
        h.append('</blockquote>')
        h.append('<p class="xpost-foot" dir="auto"><a href="%s" target="_blank" '
                 'rel="noopener nofollow">%s</a> \u00b7 %s</p>'
                 % (esc(post["url"]), esc(post["linklabel"]), esc(post["note"])))
    for num, claim, check, verdict, hot in d["rows"]:
        h.append('<div class="f5-row%s"><span class="f5-n">%s</span>'
                 '<div class="f5-b"><h4>%s</h4><p>%s</p>%s</div></div>'
                 % (" hot" if hot else "", esc(num), esc(claim), esc(check), chip(verdict, 0)))
    h.append('<p class="punch punch-bar">%s</p>' % esc(d["punch"]))
    h.append(figfoot(d) + "</figure>")
    return "".join(h)


BUILDERS = {1: fig1, 2: fig2, 3: fig3, 4: fig4, 5: fig5}

PHOTOS = {
    "en": {
        1: dict(file="gaza-airport-1998-arafat-clinton.jpg",
                alt="Yasser Arafat and Bill Clinton cut the ribbon at Gaza International Airport in 1998, Suha Arafat behind them",
                cap="Yasser Arafat and US President Bill Clinton cut the ribbon at Gaza International Airport on 14 December 1998; Suha Arafat stands behind them. The airport was the Oslo era\u2019s proudest artifact \u2014 and, like the era, did not survive. White House photograph, public domain."),
        2: dict(file="suha-arafat-hillary-clinton-gaza-1998.jpg",
                alt="Suha Arafat accompanies First Lady Hillary Clinton at a women's event in Gaza in 1998",
                cap="Suha Arafat, right, accompanies First Lady Hillary Clinton at a women\u2019s event in Gaza, 14 December 1998 \u2014 five years before the Paris inquiry that never became a case. White House photograph, public domain."),
        3: dict(file="zahwa-silla-malta-arrival.jpg",
                alt="Zahwa Arafat carries Silla, a wounded girl evacuated from Gaza, on her arrival in Malta",
                cap="Zahwa Arafat carries Silla \u2014 a girl wounded in Gaza who lost both her parents \u2014 on the child\u2019s arrival in Malta for treatment. Photograph obtained by Times of Palestine."),
        4: dict(file="zahwa-silla-malta.jpg",
                alt="Zahwa Arafat with Silla in Malta",
                cap="Zahwa Arafat with Silla in Malta. Receiving Gaza\u2019s evacuated children for treatment in Maltese hospitals is among her duties with the Palestinian embassy. Photograph obtained by Times of Palestine."),
        5: dict(file="zahwa-graduation-malta-2017.jpg",
                alt="Zahwa Arafat in cap and gown at her University of Malta graduation, holding her diploma, a Palestinian flag stole on her shoulders",
                cap="Zahwa Arafat at her graduation from the University of Malta, November 2017, the Palestinian flag on her stole. Photograph obtained by Times of Palestine."),
        6: dict(file="zahwa-diploma-university-of-malta.jpg",
                alt="University of Malta diploma conferring a Bachelor of Arts with honours on Zahwa El Kodwa, dated 13 November 2017",
                cap="The University of Malta diploma awarding Zahwa Arafat a Bachelor of Arts with honours, magna cum laude, on 13 November 2017. El Kodwa, the name on the document, is the Arafat family\u2019s surname, al-Qudwa. Document obtained by Times of Palestine."),
        7: dict(file="zahwa-gaza-child-malta.jpg",
                alt="Zahwa Arafat blows soap bubbles with a young girl from Gaza in Malta",
                cap="Zahwa Arafat plays with a girl from Gaza brought to Malta for treatment. Photograph obtained by Times of Palestine."),
    },
    "ar": {
        1: dict(file="gaza-airport-1998-arafat-clinton.jpg",
                alt="\u064a\u0627\u0633\u0631 \u0639\u0631\u0641\u0627\u062a \u0648\u0628\u064a\u0644 \u0643\u0644\u064a\u0646\u062a\u0648\u0646 \u064a\u0642\u0635\u0651\u0627\u0646 \u0634\u0631\u064a\u0637 \u0645\u0637\u0627\u0631 \u063a\u0632\u0629 \u0627\u0644\u062f\u0648\u0644\u064a \u0639\u0627\u0645 1998 \u0648\u062e\u0644\u0641\u0647\u0645\u0627 \u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062a",
                cap="\u064a\u0627\u0633\u0631 \u0639\u0631\u0641\u0627\u062a \u0648\u0627\u0644\u0631\u0626\u064a\u0633 \u0627\u0644\u0623\u0645\u064a\u0631\u0643\u064a \u0628\u064a\u0644 \u0643\u0644\u064a\u0646\u062a\u0648\u0646 \u064a\u0642\u0635\u0651\u0627\u0646 \u0634\u0631\u064a\u0637 \u0627\u0641\u062a\u062a\u0627\u062d \u0645\u0637\u0627\u0631 \u063a\u0632\u0629 \u0627\u0644\u062f\u0648\u0644\u064a \u0641\u064a 14 \u0643\u0627\u0646\u0648\u0646 \u0627\u0644\u0623\u0648\u0644 1998\u060c \u0648\u062e\u0644\u0641\u0647\u0645\u0627 \u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062a. \u0643\u0627\u0646 \u0627\u0644\u0645\u0637\u0627\u0631 \u0623\u0632\u0647\u0649 \u062b\u0645\u0627\u0631 \u0645\u0631\u062d\u0644\u0629 \u0623\u0648\u0633\u0644\u0648 \u2014 \u0648\u0644\u0645 \u064a\u0643\u062a\u0628 \u0644\u0647 \u0627\u0644\u0628\u0642\u0627\u0621 \u0645\u062b\u0644\u0647\u0627. \u062a\u0635\u0648\u064a\u0631 \u0627\u0644\u0628\u064a\u062a \u0627\u0644\u0623\u0628\u064a\u0636 \u2014 \u0645\u0644\u0643\u064a\u0629 \u0639\u0627\u0645\u0629."),
        2: dict(file="suha-arafat-hillary-clinton-gaza-1998.jpg",
                alt="\u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062a \u062a\u0631\u0627\u0641\u0642 \u0647\u064a\u0644\u0627\u0631\u064a \u0643\u0644\u064a\u0646\u062a\u0648\u0646 \u0641\u064a \u063a\u0632\u0629 \u0639\u0627\u0645 1998",
                cap="\u0633\u0647\u0649 \u0639\u0631\u0641\u0627\u062a (\u0625\u0644\u0649 \u0627\u0644\u064a\u0645\u064a\u0646) \u062a\u0631\u0627\u0641\u0642 \u0627\u0644\u0633\u064a\u062f\u0629 \u0627\u0644\u0623\u0645\u064a\u0631\u0643\u064a\u0629 \u0627\u0644\u0623\u0648\u0644\u0649 \u0647\u064a\u0644\u0627\u0631\u064a \u0643\u0644\u064a\u0646\u062a\u0648\u0646 \u0641\u064a \u0644\u0642\u0627\u0621 \u0646\u0633\u0627\u0626\u064a \u0628\u063a\u0632\u0629\u060c 14 \u0643\u0627\u0646\u0648\u0646 \u0627\u0644\u0623\u0648\u0644 1998 \u2014 \u0642\u0628\u0644 \u062e\u0645\u0633 \u0633\u0646\u0648\u0627\u062a \u0645\u0646 \u062a\u062d\u0642\u064a\u0642 \u0628\u0627\u0631\u064a\u0633 \u0627\u0644\u0630\u064a \u0644\u0645 \u064a\u0635\u0631 \u0642\u0636\u064a\u0629. \u062a\u0635\u0648\u064a\u0631 \u0627\u0644\u0628\u064a\u062a \u0627\u0644\u0623\u0628\u064a\u0636 \u2014 \u0645\u0644\u0643\u064a\u0629 \u0639\u0627\u0645\u0629."),
        3: dict(file="zahwa-silla-malta-arrival.jpg",
                alt="زهوة عرفات تحمل سيلا، طفلة جريحة من غزة، لدى وصولها إلى مالطا",
                cap="زهوة عرفات تحمل سيلا — طفلة جُرحت في غزة وفقدت والديها — لدى وصول الطفلة إلى مالطا للعلاج. صورة حصلت عليها تايمز أوف فلسطين."),
        4: dict(file="zahwa-silla-malta.jpg",
                alt="زهوة عرفات مع سيلا في مالطا",
                cap="زهوة عرفات مع سيلا في مالطا. من مهامها مع السفارة الفلسطينية استقبال أطفال غزة القادمين للعلاج في مستشفيات مالطا. صورة حصلت عليها تايمز أوف فلسطين."),
        5: dict(file="zahwa-graduation-malta-2017.jpg",
                alt="زهوة عرفات بزيّ التخرج في جامعة مالطا حاملة شهادتها وعلى كتفيها وشاح العلم الفلسطيني",
                cap="زهوة عرفات في حفل تخرجها من جامعة مالطا، تشرين الثاني ٢٠١٧، والعلم الفلسطيني على وشاحها. صورة حصلت عليها تايمز أوف فلسطين."),
        6: dict(file="zahwa-diploma-university-of-malta.jpg",
                alt="شهادة جامعة مالطا بمنح زهوة القدوة درجة البكالوريوس في الآداب بمرتبة الشرف بتاريخ ١٣ تشرين الثاني ٢٠١٧",
                cap="شهادة جامعة مالطا بمنح زهوة عرفات درجة البكالوريوس في الآداب بمرتبة الشرف مع الامتياز، بتاريخ ١٣ تشرين الثاني ٢٠١٧. والاسم المدوَّن في الشهادة، «القدوة»، هو اسم عائلة عرفات الأصلي. وثيقة حصلت عليها تايمز أوف فلسطين."),
        7: dict(file="zahwa-gaza-child-malta.jpg",
                alt="زهوة عرفات تنفخ فقاعات صابون مع طفلة من غزة في مالطا",
                cap="زهوة عرفات تلعب مع طفلة من غزة تُعالَج في مالطا. صورة حصلت عليها تايمز أوف فلسطين."),
    },
}


def photo(d):
    return ('<figure class="photo"><img src="media/%s" alt="%s" loading="lazy">'
            '<figcaption>%s</figcaption></figure>'
            % (esc(d["file"]), esc(d["alt"]), esc(d["cap"])))

CSS = """
:root{--paper:#F4F6F0;--card:#FFFFFF;--ink:#14201B;--ink2:#55655C;--rule:#C9D3C2;
--rule2:#E2E8DD;--slate:#1D3A57;--slate-bg:#DCE4EC;--red:#A6291F;--red-bg:#F2DEDB;--max:1120px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
font-family:'IBM Plex Serif',Georgia,'Times New Roman',serif;font-size:19px;line-height:1.68}
body[dir=rtl]{font-family:'IBM Plex Sans Arabic','Noto Sans Arabic',system-ui,sans-serif;
font-size:19px;line-height:1.95}
.mono{font-family:'IBM Plex Mono',ui-monospace,Consolas,monospace}
body[dir=rtl] .mono{font-family:'IBM Plex Sans Arabic',system-ui,sans-serif}
.wrap{max-width:var(--max);margin:0 auto;padding:0 24px}
.col{max-width:680px;margin:0 auto}

/* masthead */
.top{border-top:6px solid var(--ink);border-bottom:1px solid var(--rule);background:var(--card)}
.top .wrap{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-block:14px;flex-wrap:wrap}
.mast{font-weight:600;letter-spacing:.2em;font-size:13px;margin:0;text-transform:uppercase}
body[dir=rtl] .mast{letter-spacing:0}
.lang{font-size:12px;text-decoration:none;color:var(--ink);border:1px solid var(--rule);
padding:5px 12px;border-radius:2px}
.lang:hover{background:var(--paper)}

/* hero */
header.hero{padding:56px 0 32px}
.eyebrow{color:var(--red);font-size:11.5px;letter-spacing:.18em;font-weight:600;margin:0 0 20px;text-transform:uppercase}
body[dir=rtl] .eyebrow{letter-spacing:0}
h1{font-size:clamp(34px,5.6vw,58px);line-height:1.1;margin:0 0 20px;font-weight:600;letter-spacing:-.015em}
body[dir=rtl] h1{line-height:1.35;letter-spacing:0}
.deck{font-size:clamp(18px,2.2vw,23px);line-height:1.45;color:var(--ink2);margin:0 0 28px;font-weight:400}
body[dir=rtl] .deck{line-height:1.75}
.byline{border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:12px 0;
font-size:12px;letter-spacing:.08em;color:var(--ink2);display:flex;gap:18px;flex-wrap:wrap}
body[dir=rtl] .byline{letter-spacing:0}

/* body */
article{padding-bottom:64px}
article p{margin:0 0 22px}
article h2{font-size:clamp(22px,3vw,29px);line-height:1.25;margin:56px 0 22px;font-weight:600;
padding-top:22px;border-top:2px solid var(--ink)}
body[dir=rtl] article h2{line-height:1.5}
article strong{font-weight:600}
article em{font-style:italic}
body[dir=rtl] article em{font-style:normal;border-bottom:1px dotted var(--ink2)}
article hr{border:0;border-top:1px solid var(--rule);margin:44px 0}
article a{color:var(--slate)}
article>.col:first-child>p:first-of-type::first-letter{font-size:3.1em;line-height:.86;float:left;
margin:6px 10px 0 0;font-weight:600;color:var(--ink)}
body[dir=rtl] article>.col:first-child>p:first-of-type::first-letter{float:right;margin:6px 0 0 10px}

/* chips */
.chip{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.06em;
padding:4px 9px;border-radius:2px;white-space:nowrap;line-height:1.4;
font-family:'IBM Plex Mono',ui-monospace,monospace;text-transform:uppercase}
body[dir=rtl] .chip{font-family:'IBM Plex Sans Arabic',sans-serif;letter-spacing:0;text-transform:none}
.chip.no{background:var(--red-bg);color:var(--red)}
.chip.ok{background:var(--slate-bg);color:var(--slate)}

/* figures */
.fig{margin:44px auto;background:var(--card);border:1px solid var(--rule);
border-top:5px solid var(--ink);padding:26px 24px 20px;max-width:900px}
.fig-n{margin:0 0 10px;font-size:11px;letter-spacing:.14em;font-weight:600;color:var(--red);
font-family:'IBM Plex Mono',ui-monospace,monospace;text-transform:uppercase}
body[dir=rtl] .fig-n{font-family:'IBM Plex Sans Arabic',sans-serif;letter-spacing:0;text-transform:none}
.fig-n span{color:var(--ink2)}
.fig h3{margin:0 0 6px;font-size:clamp(19px,2.4vw,25px);line-height:1.22;font-weight:600}
body[dir=rtl] .fig h3{line-height:1.45}
.fig-s{margin:0 0 20px;font-size:14px;line-height:1.5;color:var(--ink2)}
body[dir=rtl] .fig-s{line-height:1.75}
.fig-src{margin:16px 0 0;padding-top:12px;border-top:1px solid var(--rule);
font-size:11.5px;color:var(--ink2);line-height:1.5}
.lab{margin:14px 0 6px;font-size:10.5px;letter-spacing:.12em;font-weight:600;color:var(--ink2);
font-family:'IBM Plex Mono',ui-monospace,monospace;text-transform:uppercase}
body[dir=rtl] .lab{font-family:'IBM Plex Sans Arabic',sans-serif;letter-spacing:0;text-transform:none}
.lab-b{color:var(--slate)}
.punch{margin:22px 0 0;font-size:15px;font-weight:600;color:var(--red);
font-family:'IBM Plex Mono',ui-monospace,monospace;line-height:1.5}
body[dir=rtl] .punch{font-family:'IBM Plex Sans Arabic',sans-serif}
.punch-bar{background:var(--ink);color:var(--paper);padding:16px 18px;text-align:center;border-radius:2px}
.note{margin:18px 0 0;padding:14px 16px;background:var(--paper);
border-inline-start:3px solid var(--ink2);font-size:13.5px;line-height:1.55;color:var(--ink2)}
body[dir=rtl] .note{line-height:1.8}

/* f1 */
.f1-head,.f2-head{display:grid;gap:14px;font-size:10.5px;letter-spacing:.11em;font-weight:600;
color:var(--ink2);padding-bottom:8px;border-bottom:1px solid var(--rule);
font-family:'IBM Plex Mono',ui-monospace,monospace;text-transform:uppercase}
body[dir=rtl] .f1-head,body[dir=rtl] .f2-head{font-family:'IBM Plex Sans Arabic',sans-serif;letter-spacing:0;text-transform:none}
.f1-head{grid-template-columns:150px 1fr 170px}
.f1-row{display:grid;grid-template-columns:150px 1fr 170px;gap:14px;align-items:center;
padding:14px 0;border-bottom:1px solid var(--rule2)}
.f1-bar{position:relative;padding:7px 10px;border-radius:2px;min-width:88px}
.f1-bar::before{content:"";position:absolute;inset:0;width:var(--w);border-radius:2px;opacity:.2}
.f1-row.no .f1-bar::before{background:var(--red)}
.f1-row.ok .f1-bar::before{background:var(--slate)}
.f1-row.no .f1-bar{border-inline-start:3px solid var(--red)}
.f1-row.ok .f1-bar{border-inline-start:3px solid var(--slate)}
.f1-amt{position:relative;font-size:17px;font-weight:600;
font-family:'IBM Plex Mono',ui-monospace,monospace}
body[dir=rtl] .f1-amt{font-family:'IBM Plex Sans Arabic',sans-serif}
.f1-who{margin:0;font-size:13.5px;line-height:1.5;color:var(--ink2)}
body[dir=rtl] .f1-who{line-height:1.75}

/* f2 */
.f2-head{grid-template-columns:1fr 1.35fr}
.f2-row{display:grid;grid-template-columns:1fr 1.35fr;gap:20px;padding:16px 0;
border-bottom:1px solid var(--rule2)}
.f2-row p{margin:0}
.f2-c{font-size:14.5px;font-weight:600;line-height:1.45;padding-inline-start:12px}
body[dir=rtl] .f2-c{line-height:1.7}
.f2-row.no .f2-c{border-inline-start:4px solid var(--red)}
.f2-row.ok .f2-c{border-inline-start:4px solid var(--slate)}
.f2-r{font-size:13.5px;line-height:1.55;color:var(--ink2)}
body[dir=rtl] .f2-r{line-height:1.8}
.f2-key{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}

/* f3 */
.f3-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px}
.f3-col{border-top:5px solid var(--ink);padding-top:12px}
.f3-when{margin:0 0 8px;font-size:10.5px;letter-spacing:.1em;font-weight:600;color:var(--red);
font-family:'IBM Plex Mono',ui-monospace,monospace}
body[dir=rtl] .f3-when{font-family:'IBM Plex Sans Arabic',sans-serif;letter-spacing:0}
.f3-col h4{margin:0 0 4px;font-size:16.5px;line-height:1.25;font-weight:600}
body[dir=rtl] .f3-col h4{line-height:1.5}
.f3-t{margin:0;font-size:13px;line-height:1.5}
body[dir=rtl] .f3-t{line-height:1.75}
.f3-b{color:var(--ink2);border-top:1px solid var(--rule);padding-top:10px;margin-top:-2px}

/* f4 */
.f4-grid{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.f4-p h4{margin:0 0 4px;font-size:19px;font-weight:600;padding-inline-start:12px}
.f4-p.doc h4{border-inline-start:5px solid var(--slate)}
.f4-p.no h4{border-inline-start:5px solid var(--red)}
.f4-p ul{margin:0;padding:0;list-style:none}
.f4-p li{font-size:13.5px;line-height:1.5;margin:0 0 12px;padding-inline-start:12px}
body[dir=rtl] .f4-p li{line-height:1.75}
.f4-a li{border-inline-start:3px solid var(--rule)}
.f4-p.doc .f4-a li{border-inline-start-color:var(--slate)}
.f4-p.no .f4-a li{border-inline-start-color:var(--red)}
.f4-b{border-top:1px solid var(--rule);padding-top:12px!important}
.f4-b li{color:var(--ink2);border-inline-start:3px solid var(--rule2)}

/* photos */
.photo{margin:44px auto;max-width:900px}
.photo img{width:100%;height:auto;display:block;border:1px solid var(--rule)}
.photo figcaption{margin-top:10px;font-size:13px;line-height:1.55;color:var(--ink2)}

/* f5 */
.xpost{margin:0 0 8px;padding:16px 18px;background:var(--paper);border:1px solid var(--rule);
border-inline-start:4px solid var(--red);border-radius:2px;direction:ltr;text-align:left}
.xpost-meta{margin:0 0 8px;font-size:12px;color:var(--ink2);letter-spacing:.04em;
font-family:'IBM Plex Mono',ui-monospace,monospace}
.xpost-name{font-weight:700;color:var(--ink)}
.xpost-text{margin:0;font-size:15.5px;line-height:1.6}
.xpost-foot{margin:0 0 20px;font-size:12px;color:var(--ink2)}
.xpost-foot a{color:var(--slate)}

.f5-row{display:grid;grid-template-columns:56px 1fr;gap:12px;padding:16px 12px;
border-bottom:1px solid var(--rule2);border-radius:2px}
.f5-row.hot{background:#FBF2F1}
.f5-n{font-size:25px;font-weight:700;color:var(--rule);line-height:1;
font-family:'IBM Plex Mono',ui-monospace,monospace}
.f5-b h4{margin:0 0 6px;font-size:16.5px;font-weight:600;line-height:1.3}
body[dir=rtl] .f5-b h4{line-height:1.55}
.f5-b p{margin:0 0 10px;font-size:13.5px;line-height:1.55;color:var(--ink2)}
body[dir=rtl] .f5-b p{line-height:1.8}

footer.foot{border-top:2px solid var(--ink);background:var(--card);padding:28px 0 44px;
font-size:12.5px;color:var(--ink2);line-height:1.6}
body[dir=rtl] footer.foot{line-height:1.85}

@media(max-width:860px){
 .f3-grid{grid-template-columns:1fr 1fr}
 .f4-grid{grid-template-columns:1fr;gap:22px}
 .f2-head{display:none}
 .f2-row{grid-template-columns:1fr;gap:10px}
 .f2-r{padding-inline-start:12px;border-inline-start:1px dotted var(--rule)}
}
@media(max-width:620px){
 body{font-size:17.5px}
 .fig{padding:20px 16px 16px;margin-inline:-8px}
 .f3-grid{grid-template-columns:1fr}
 .f1-head{display:none}
 .f1-row{grid-template-columns:1fr;gap:8px}
 .f1-bar{max-width:200px}
 .f5-row{grid-template-columns:1fr}
 .f5-n{font-size:16px}
 article>.col:first-child>p:first-of-type::first-letter{font-size:2.4em}
}
@media print{
 body{background:#fff;font-size:11pt}
 .top,.lang{display:none}
 .fig{break-inside:avoid;page-break-inside:avoid}
}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

SHELL = """<!DOCTYPE html>
<html lang="{lang}" dir="{dir}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} \u2014 {masthead}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="article">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans+Arabic:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
</head>
<body dir="{dir}">
<div class="top"><div class="wrap">
  <p class="mast">{masthead}</p>
  <a class="lang" href="{otherhref}">{other}</a>
</div></div>
<div class="wrap">
  <header class="hero col">
    <p class="eyebrow">{section}</p>
    <h1>{title}</h1>
    <p class="deck">{deck}</p>
    <div class="byline mono"><span>{date}</span><span>{readtime}</span></div>
  </header>
  <article>{body}</article>
</div>
<footer class="foot"><div class="wrap col">{footnote}</div></footer>
</body></html>
"""


def build(lang):
    md = open(os.path.join(HERE, "article-%s.md" % lang), encoding="utf-8").read()
    lines = md.split("\n")
    title = lines[0].lstrip("# ").strip()
    deck = next(l for l in lines[1:] if l.startswith("## ")).lstrip("# ").strip()
    rest = md.split(deck, 1)[1].lstrip("\n").lstrip("-").lstrip("\n")

    # split off the closing italic note
    parts = rest.rsplit("\n\n*", 1)
    body_md, foot = parts[0], "*" + parts[1]

    placeholders = {}
    for i in range(1, 6):
        key = "FIGPLACEHOLDER%d" % i
        placeholders[key] = BUILDERS[i](FIGS[lang][i])
        body_md = body_md.replace("[[FIG%d]]" % i, key)
    for i, d in PHOTOS[lang].items():
        key = "PHOTOPLACEHOLDER%d" % i
        placeholders[key] = photo(d)
        body_md = body_md.replace("[[PHOTO%d]]" % i, key)

    html_body = markdown.markdown(body_md, extensions=["extra"])
    html_body = '<div class="col">' + html_body + "</div>"
    for key, block in placeholders.items():
        html_body = html_body.replace("<p>%s</p>" % key,
                                      '</div>%s<div class="col">' % block)

    m = META[lang]
    words = len(re.sub(r"<[^>]+>", " ", html_body).split())
    rt = {"en": "%d min read" % max(1, round(words / 220)),
          "ar": "\u0642\u0631\u0627\u0621\u0629 %d \u062F\u0642\u064A\u0642\u0629" % max(1, round(words / 180))}[lang]
    date = {"en": "31 July 2026", "ar": "\u0663\u0661 \u062A\u0645\u0651\u0648\u0632 \u0662\u0660\u0662\u0666"}[lang]

    page = SHELL.format(lang=m["lang"], dir=m["dir"], title=esc(title), masthead=esc(m["masthead"]),
                        desc=esc(m["desc"]), section=esc(m["section"]), deck=esc(deck),
                        date=date, readtime=rt, body=html_body,
                        footnote=markdown.markdown(foot),
                        other=esc(m["other"]), otherhref=m["otherhref"])
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "index-%s.html" % lang), "w", encoding="utf-8").write(page)
    print("built", "index-%s.html" % lang, "(%d words)" % words)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "style.css"), "w", encoding="utf-8").write(CSS)
    for lg in ("en", "ar"):
        build(lg)
