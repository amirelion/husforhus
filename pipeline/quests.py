"""Stockholm's quests: short walks through the city as riddles (the mechanics are upstream's, the content is ours).

Amsterdam's pipeline/quests.py (reference/amsterdam/) is not reused: its places, articles and photos are Amsterdam's.
Each step here names a curated landmark (pipeline/landmarks.py) by `at="lm:<name>"`; s13_quests resolves it to the
landmark's gid through data/years.parquet, so a step can only point at a building whose year the map already takes
from a checked article. Three kinds of step, as the viewer plays them (web/app.js, Quests):

  find    a riddle; the player finds the building on the map and clicks it. The first hint draws a circle around
          it, later hints are the `hints` texts; "Show me" flies there for no crosses.
  year    the map flies to the building and hides its age; the player guesses the year it was built. `year` must be
          the map's year for that building (s13_quests checks it), so the card opened next tells the same story.
  choice  the map flies to the building; the player picks one of three answers (the right one first; the page
          shuffles them).

`checks`: [(source, [strings])]: the cited article ("sv:Title", as in pipeline/landmarks.py) must contain each
string, compared as s08_landmarks compares (s08_landmarks.norm). Every fact in a riddle, hint, option or reveal is
covered by one of them. Levels: 1 easy, 2 medium, 3 hard. Texts in English and Swedish ({"en", "sv"}).
"""


def T(en, sv):
    return dict(en=en, sv=sv)


def find(at, riddle, hints, reveal, checks, mode=None):
    return dict(kind="find", at=at, riddle=riddle, hints=hints, reveal=reveal, checks=list(checks), mode=mode)


def year(at, ask, answer, reveal, checks):
    return dict(kind="year", at=at, ask=ask, year=answer, reveal=reveal, checks=list(checks))


def choice(at, ask, options, reveal, checks):
    """options: the right answer first; the page shuffles them."""
    return dict(kind="choice", at=at, ask=ask, options=options, reveal=reveal, checks=list(checks))


QUESTS = [
    dict(id="gamla-stan", level=1,
         title=T("Around the old town", "Runt Gamla stan"),
         intro=T("Five buildings on Stadsholmen and Riddarholmen: a cathedral, a palace, two churches and the house "
                 "of the nobility.",
                 "Fem byggnader på Stadsholmen och Riddarholmen: en domkyrka, ett slott, två kyrkor och adelns hus."),
         steps=[
             find("lm:Storkyrkan",
                  T("Stockholm's cathedral stands between the palace and the old square. Find it.",
                    "Stockholms domkyrka står mellan slottet och det gamla torget. Hitta den."),
                  [T("Its other name is Sankt Nicolai kyrka.", "Den heter också Sankt Nicolai kyrka.")],
                  T("Storkyrkan. Royal coronations have been held here since the 1300s, and the Reformation in Sweden "
                    "began here while Olaus Petri was its priest.",
                    "Storkyrkan. Här har kungliga kröningar hållits sedan 1300-talet, och reformationen i Sverige "
                    "inleddes här under Olaus Petris tid som präst."),
                  [("sv:Storkyrkan", ["mellan Stockholms slott och Stortorget", "Sankt Nicolai kyrka",
                                      "kungliga kröningar", "Olaus Petris tid som präst"])]),
             year("lm:Riddarholmskyrkan",
                  T("The burial church of Sweden's monarchs. When was it consecrated?",
                    "De svenska monarkernas gravkyrka. När invigdes den?"),
                  1292,
                  T("About 1292, when Magnus Ladulås was buried here. It is Stockholm's oldest surviving building.",
                    "Cirka 1292, då Magnus Ladulås begravdes här. Den är Stockholms äldsta bevarade byggnad."),
                  [("sv:Riddarholmskyrkan", ["invigd cirka år 1292, då Magnus Ladulås begravdes",
                                             "Stockholms äldsta bevarade byggnad", "monarkernas gravkyrka"])]),
             find("lm:Tyska kyrkan",
                  T("The highest point of the old town is the cockerel on this church's tower. Find the church.",
                    "Gamla stans högsta punkt är tuppen på den här kyrkans torn. Hitta kyrkan."),
                  [T("It is also called Sankta Gertruds kyrka, and stands on Svartmangatan.",
                     "Den kallas också Sankta Gertruds kyrka och ligger vid Svartmangatan.")],
                  T("Tyska kyrkan, the German church: the cockerel on its tower is 96 metres above the water.",
                    "Tyska kyrkan: tuppen på tornet sitter 96 meter över vattnet."),
                  [("sv:Tyska kyrkan, Stockholm", ["Gamla stans högsta punkt är tuppen på Tyska kyrkans torn",
                                                   "96 meter över vattnet", "Sankta Gertruds kyrka",
                                                   "Svartmangatan"])]),
             choice("lm:Riddarhuset",
                    T("Riddarhuset is owned by Sweden's nobility. Which building in another country is it closely "
                      "copied from, apart from the roof?",
                      "Riddarhuset ägs av Sveriges ridderskap och adel. Vilken byggnad i ett annat land är det, "
                      "utom taket, ganska nära kopierat efter?"),
                    [T("Mauritshuis in The Hague", "Mauritshuis i Haag"),
                     T("The Louvre in Paris", "Louvren i Paris"),
                     T("The Doge's Palace in Venice", "Dogepalatset i Venedig")],
                    T("Mauritshuis in The Hague. The first architect was Simon de la Vallée; the palace was built "
                      "1641-1674.",
                      "Mauritshuis i Haag. Den förste arkitekten var Simon de la Vallée; palatset uppfördes "
                      "1641-1674."),
                    [("sv:Riddarhuspalatset", ["Sveriges ridderskap och adel", "Mauritshuis i Haag",
                                               "Simon de la Vallée", "uppfört 1641-1674"])]),
             year("lm:Stockholms slott",
                  T("The royal palace replaced Tre Kronor, which burned in 1697. When could the king move in?",
                    "Slottet ersatte Tre Kronor, som brann 1697. När kunde kungen flytta in?"),
                  1754,
                  T("1754, when Adolf Fredrik and Lovisa Ulrika moved in. Nicodemus Tessin the Younger drew it.",
                    "1754, då Adolf Fredrik och Lovisa Ulrika flyttade in. Nicodemus Tessin den yngre ritade det."),
                  [("sv:Stockholms slott", ["brand den 7 maj 1697", "Slottet kunde inte tas i bruk förrän 1754",
                                            "Adolf Fredrik och drottning Lovisa Ulrika flyttade in",
                                            "ritad av Nicodemus Tessin den yngre"])]),
         ]),
]
