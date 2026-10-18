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

    dict(id="city", level=1,
         title=T("Through the city centre", "Genom city"),
         intro=T("Six buildings on Norrmalm, Blasieholmen and Kungsholmen: an opera house and its twin palace, a church, "
                 "a house of culture, an art museum and the city hall.",
                 "Sex byggnader på Norrmalm, Blasieholmen och Kungsholmen: ett operahus och dess tvillingpalats, en "
                 "kyrka, ett kulturhus, ett konstmuseum och stadshuset."),
         steps=[
             find("lm:Kungliga Operan",
                  T("Sweden's national stage for opera and ballet stands between Gustav Adolfs torg and "
                    "Kungsträdgården. Find it.",
                    "Sveriges nationalscen för opera och balett ligger mellan Gustav Adolfs torg och Kungsträdgården. "
                    "Hitta den."),
                  [T("Its architect, Axel Anderberg, took much of his inspiration from the Paris Opera.",
                     "Arkitekten Axel Anderberg hämtade mycket inspiration från Parisoperan.")],
                  T("Kungliga Operan, opened on 19 September 1898. In the opera house that stood here before it, "
                    "Gustav III was shot at a masked ball on 16 March 1792.",
                    "Kungliga Operan, som togs i bruk den 19 september 1898. I operahuset som stod här före det mördades "
                    "Gustav III vid en maskeradbal den 16 mars 1792."),
                  [("sv:Kungliga Operan", ["Sveriges nationalscen för opera och balett",
                                           "mellan Gustav Adolfs torg och Kungsträdgården",
                                           "hämtade mycket inspiration från Parisoperan",
                                           "Den 19 september 1898 kunde det nuvarande operahuset",
                                           "Den 16 mars 1792 mördades kungen vid en maskeradbal"])]),
             choice("lm:Arvfurstens palats",
                    T("Across the square, Arvfurstens palats was built as a pendant to the old opera house. Who has "
                      "used it since 1906?",
                      "Mitt emot på torget byggdes Arvfurstens palats som en pendang till det gamla operahuset. Vem har "
                      "använt det sedan 1906?"),
                    [T("The Ministry for Foreign Affairs", "Utrikesdepartementet"),
                     T("The Riksdag", "Riksdagen"),
                     T("The Royal Court", "Hovet")],
                    T("The Ministry for Foreign Affairs. The palace was built between 1783 and 1794 for Princess Sofia "
                      "Albertina, Gustav III's sister.",
                      "Utrikesdepartementet. Palatset uppfördes mellan 1783 och 1794 för prinsessan Sofia Albertina, "
                      "Gustav III:s syster."),
                    [("sv:Arvfurstens palats", ["pendang till det just färdigställda Gustavianska operahuset",
                                                "används sedan 1906 av Utrikesdepartementet",
                                                "uppfört mellan 1783 och 1794 för prinsessan Sofia Albertina, syster "
                                                "till kung Gustav III"])]),
             find("lm:Klara kyrka",
                  T("Its 116-metre tower makes it the second-tallest church in Sweden and Scandinavia, after Uppsala "
                    "Cathedral. Find it on Norrmalm.",
                    "Med sitt 116 meter höga torn är den Sveriges och Skandinaviens näst högsta kyrka, efter Uppsala "
                    "domkyrka. Hitta den på Norrmalm."),
                  [T("It is named after the convent of Sankta Klara that once stood on the site.",
                     "Den har fått sitt namn efter Sankta Klara kloster, som låg på platsen.")],
                  T("Klara kyrka. Gustav Vasa had the convent and its church pulled down in 1527; Johan III built the "
                    "church that stands here.",
                    "Klara kyrka. Gustav Vasa lät riva klostret och kyrkan 1527; Johan III lät uppföra den kyrka som "
                    "står här."),
                  [("sv:Klara kyrka", ["116 meter höga torn", "Sveriges och Skandinaviens näst högsta kyrka, efter "
                                       "Uppsala domkyrka", "Sankta Klara kloster",
                                       "Gustav Vasa lät riva klostret och kyrkan 1527",
                                       "Den nuvarande kyrkan lät Johan III uppföra"])]),
             choice("lm:Kulturhuset",
                    T("Kulturhuset, on the south side of Sergels torg, opened its first part in 1971. Who moved in?",
                      "Kulturhuset vid Sergels torgs södra sida öppnade sin första etapp 1971. Vem flyttade in?"),
                    [T("The Riksdag, in temporary premises", "Riksdagen, i provisoriska lokaler"),
                     T("Moderna Museet", "Moderna Museet"),
                     T("The Royal Library", "Kungliga biblioteket")],
                    T("The Riksdag. Moderna Museet had been part of the plan but pulled out in early 1970. Peter "
                      "Celsing won the competition, and the whole building was in use in 1974.",
                      "Riksdagen. Moderna Museet hade varit med i planerna men klev av i början av 1970. Peter Celsing "
                      "vann tävlingen, och hela anläggningen togs i drift 1974."),
                    [("sv:Kulturhuset, Stockholm", ["vid södra sidan av Sergels torg",
                                                    "Byggnadens första etapp öppnades 1971 för riksdagens provisoriska "
                                                    "lokaler", "I början av 1970 klev Moderna Museet av satsningen",
                                                    "vanns av arkitekten Peter Celsing",
                                                    "Hela anläggningen togs i drift år 1974"])]),
             year("lm:Nationalmuseum",
                  T("The art museum on Blasieholmen was drawn by the German Friedrich August Stüler, who had designed "
                    "the Neues Museum in Berlin. When was it inaugurated?",
                    "Konstmuseet på Blasieholmen ritades av tysken Friedrich August Stüler, som hade ritat Neues Museum "
                    "i Berlin. När invigdes det?"),
                  1866,
                  T("On 15 June 1866, together with the Stockholm Exhibition of 1866. On the water, it was to be a "
                    "natural counterpart to the royal palace.",
                    "Den 15 juni 1866, samtidigt med Stockholmsutställningen 1866. Vid Strömmen skulle det bli en "
                    "naturlig pendang till slottet."),
                  [("sv:Nationalmuseum (byggnad)", ["tyske arkitekten Friedrich August Stüler",
                                                    "Han hade bland annat ritat Neues Museum i Berlin",
                                                    "Byggnaden invigdes den 15 juni 1866 samtidigt med "
                                                    "Stockholmsutställningen 1866",
                                                    "placering vid Strömmen",
                                                    "en naturlig pendang till Stockholms slott"])]),
             year("lm:Stockholms stadshus",
                  T("The city hall on Kungsholmen, where the Nobel banquet is held, has three gold crowns on its tower. "
                    "When was it inaugurated?",
                    "Stadshuset på Kungsholmen, där Nobelfesten hålls, har tre kronor på tornet. När invigdes det?"),
                  1923,
                  T("On Midsummer Eve, 23 June 1923, 400 years after Gustav Vasa entered Stockholm. Ragnar Östberg drew "
                    "it; its tower is 106 metres high.",
                    "Midsommaraftonen den 23 juni 1923, fyrahundra år efter Gustav Vasas intåg i Stockholm. Ragnar "
                    "Östberg ritade det; tornet är 106 meter högt."),
                  [("sv:Stockholms stadshus", ["Nobelfesten, som hålls i Blå hallen",
                                               "tornspira med tre kronor högst upp",
                                               "invigdes midsommaraftonen den 23 juni 1923",
                                               "fyrasekelsminnet av Gustav Vasas intåg i Stockholm",
                                               "Arkitekt Ragnar Östberg", "106 meter höga torn"])]),
         ]),

    dict(id="djurgarden", level=2,
         title=T("Skeppsholmen and Djurgården", "Skeppsholmen och Djurgården"),
         intro=T("Five buildings on the islands east of the old town: a domed church, a little castle, a warship's "
                 "museum, a museum of Swedish life and one for ABBA.",
                 "Fem byggnader på öarna öster om Gamla stan: en kupolkyrka, ett litet kastell, ett regalskepps museum, "
                 "ett museum om svenskt liv och ett om ABBA."),
         steps=[
             find("lm:Skeppsholmskyrkan",
                  T("On Skeppsholmen stands an eight-sided church with a central dome, clearly inspired by the "
                    "Pantheon in Rome. Find it.",
                    "På Skeppsholmen står en åttkantig kyrka med en central kupol, tydligt inspirerad av Pantheon i Rom. "
                    "Hitta den."),
                  [T("Its official name is Karl Johans kyrka.", "Den heter officiellt Karl Johans kyrka.")],
                  T("Skeppsholmskyrkan, drawn by Fredrik Blom. It was deconsecrated on 5 December 2001 and is now a "
                    "hall for concerts.",
                    "Skeppsholmskyrkan, ritad av Fredrik Blom. Den avsakraliserades den 5 december 2001 och är i dag en "
                    "lokal för konserter."),
                  [("sv:Skeppsholmskyrkan", ["tydligt inspirerad av Pantheon i Rom", "Planformen är åttkantig",
                                             "officiellt Karl Johans kyrka", "kyrkans arkitekt var Fredrik Blom",
                                             "Den 5 december 2001 avsakraliserades Skeppsholmskyrkan",
                                             "en hall för konserter"])]),
             choice("lm:Kastellet",
                    T("Why was a new Kastellet built on Kastellholmen in the 1840s?",
                      "Varför byggdes ett nytt kastell på Kastellholmen på 1840-talet?"),
                    [T("The old one's powder store blew up in 1845", "Det gamla krutförrådet flög i luften 1845"),
                     T("The navy needed a larger barracks", "Flottan behövde en större kasern"),
                     T("Lightning burned down the old tower", "Blixten brände ner det gamla tornet")],
                    T("On 21 June 1845 its powder store, then an ammunition factory, blew up. The new castle was built "
                      "between 1846 and 1848, and Sweden's naval flag has flown here every day since the 1660s.",
                      "Den 21 juni 1845 flög krutförrådet, som användes som ammunitionsfabrik, i luften. Det nya kastellet "
                      "restes mellan 1846 och 1848, och här flaggas varje dag sedan 1660-talet med örlogsflaggan."),
                    [("sv:Kastellet, Stockholm", ["den 21 juni 1845",
                                                  "krutförrådet, som användes som ammunitionsfabrik flög i luften",
                                                  "Byggnaden restes mellan 1846 och 1848",
                                                  "flaggas varje dag sedan 1660-talet med Sveriges örlogsflagga"])]),
             year("lm:Vasamuseet",
                  T("The museum's copper roof carries stylised masts as tall as the warship Vasa when fully rigged. "
                    "When did it officially open?",
                    "Museets koppartak bär stiliserade master lika höga som regalskeppet Vasa fullt riggat. När öppnade "
                    "det officiellt?"),
                  1990,
                  T("On 15 June 1990. Prince Bertil opened the building site in 1987, and the ship, which sank on her "
                    "maiden voyage in 1628, was towed into the dry dock that December.",
                    "Den 15 juni 1990. Prins Bertil invigde bygget 1987, och skeppet, som sjönk på sin jungfruresa 1628, "
                    "bogserades in i torrdockan i december samma år."),
                  [("en:Vasa Museum", ["stylized masts that represent the actual height of Vasa when she was fully "
                                       "rigged", "The museum was officially opened on 15 June 1990",
                                       "inauguration ceremony hosted by Prince Bertil on 2 November 1987",
                                       "sank on her maiden voyage in 1628",
                                       "Vasa was towed into the flooded dry dock under the new building in December "
                                       "1987"])]),
             find("lm:Nordiska museet",
                  T("Sweden's largest museum of cultural history stands on Lejonslätten on Djurgården. Find it.",
                    "Sveriges största kulturhistoriska museum ligger på Lejonslätten på Djurgården. Hitta det."),
                  [T("Its founder, Artur Hazelius, also founded Skansen.",
                     "Grundaren Artur Hazelius grundade också Skansen.")],
                  T("Nordiska museet, built between 1889 and 1907 to drawings by Isak Gustaf Clason. Hazelius's motto "
                    "for the museum was \"Know yourself\".",
                    "Nordiska museet, uppfört mellan 1889 och 1907 efter ritningar av Isak Gustaf Clason. Hazelius motto "
                    "för museet var \"Känn dig själv\"."),
                  [("sv:Nordiska museet", ["Sveriges största kulturhistoriska museum", "ligger på Lejonslätten på "
                                           "Djurgården", "Artur Hazelius, som även grundade Skansen",
                                           "1889 och 1907 efter ritningar av arkitekt Isak Gustaf Clason",
                                           "Känn dig själv", "var Hazelius motto för Nordiska museet"])]),
             choice("lm:Abbamuseet",
                    T("ABBA The Museum opened on Djurgården on 7 May 2013. Before that the exhibition toured as "
                      "Abbaworld. Where did it open first?",
                      "Abbamuseet öppnade på Djurgården den 7 maj 2013. Innan dess turnerade utställningen som "
                      "Abbaworld. Var hade den premiär?"),
                    [T("London", "London"), T("Sydney", "Sydney"), T("New York", "New York")],
                    T("London, in January 2010. It went on to Melbourne and Sydney, then Hungary and the Czech Republic, "
                      "before it settled in Stockholm.",
                      "London, i januari 2010. Den gick vidare till Melbourne och Sydney, sedan Ungern och Tjeckien, innan "
                      "den blev permanent i Stockholm."),
                    [("sv:Abbamuseet", ["i Stockholm den 7 maj 2013", "Abbaworld, som hade premiär i London i januari "
                                        "2010", "Melbourne och Sydney i Australien, vidare till Ungern och Tjeckien "
                                        "innan den blev permanent i Stockholm"])]),
         ]),

    dict(id="sodermalm", level=2,
         title=T("Södermalm and Långholmen", "Södermalm och Långholmen"),
         intro=T("Five buildings on the southern heights: a church that burned twice, a water tower, a cinema turned "
                 "opera house, an old malmgård and a prison block.",
                 "Fem byggnader på Söders höjder: en kyrka som brunnit två gånger, ett vattentorn, en biograf som blev "
                 "operahus, en gammal malmgård och en fängelsebyggnad."),
         steps=[
             year("lm:Katarina kyrka",
                  T("The church on Högbergsgatan is named after Princess Katarina, Karl X Gustav's mother. When was it "
                    "first finished?",
                    "Kyrkan vid Högbergsgatan har fått sitt namn efter prinsessan Katarina, Karl X Gustavs mor. När stod "
                    "den klar första gången?"),
                  1695,
                  T("In 1695, to drawings by Jean de la Vallée: Sweden's first central church. It burned on 1 May 1723 "
                    "and again in May 1990, and was reconsecrated in 1995.",
                    "År 1695, efter Jean de la Vallées ritningar: Sveriges första centralkyrka. Den brann den 1 maj 1723 "
                    "och igen i maj 1990, och återinvigdes 1995."),
                  [("sv:Katarina kyrka", ["namn efter prinsessan Katarina, Karl X Gustavs mor",
                                          "Den stod klar första gången 1695", "Jean de la Vallées ritningar",
                                          "den första centralkyrkan i Sverige",
                                          "Den 1 maj 1723 förstördes kyrkan i en brand",
                                          "Natten till den 17 maj 1990 brann Katarina kyrka för andra gången",
                                          "År 1995 kunde kyrkan återinvigas"])]),
             find("lm:Mosebacke vattentorn",
                  T("An eight-sided red-brick tower, 32 metres high, once raised the water pressure for the houses high "
                    "up on Katarinaberget. Find it by Mosebacke torg.",
                    "Ett åttkantigt torn av rött tegel, 32 meter högt, ökade en gång vattentrycket för husen högt uppe på "
                    "Katarinaberget. Hitta det vid Mosebacke torg."),
                  [T("Ferdinand Boberg drew it; he may have been inspired by the corner towers of the castle of Coca in "
                     "Spain.",
                     "Ferdinand Boberg ritade det; han inspirerades möjligtvis av hörntornen på borgen i Coca i "
                     "Spanien.")],
                  T("Mosebacke vattentorn, finished in 1896. Its tank went out of use in 1960, and the tower is now a "
                    "private home.",
                    "Mosebacke vattentorn, färdigt 1896. Behållaren togs ur bruk 1960, och tornet är i dag en "
                    "privatbostad."),
                  [("sv:Mosebacke vattentorn", ["32 meter högt torn",
                                                "Den åttkantiga tornbyggnaden kläddes med rött Helsingborgstegel",
                                                "öka vattentrycket för Katarinabergets högre bebyggelse",
                                                "Mosebacke torg",
                                                "ritades av arkitekt Ferdinand Boberg och stod färdigt 1896",
                                                "hörntornen för borgen i Coca i Spanien", "togs ur bruk 1960",
                                                "omvandlat från maskinistbostad till privatbostad"])]),
             choice("lm:Folkoperan",
                    T("Folkoperan on Hornsgatan always sings in Swedish. What was its building when it opened in 1928?",
                      "Folkoperan på Hornsgatan sjunger alltid på svenska. Vad var huset när det invigdes 1928?"),
                    [T("A cinema", "En biograf"), T("A market hall", "En saluhall"), T("A fire station",
                                                                                     "En brandstation")],
                    T("A cinema, Ricardo: one of Stockholm's largest, with 1,002 seats, built where Maria saluhall had "
                      "stood. Folkoperan has played here since 1984.",
                      "En biograf, Ricardo: en av Stockholms största, med 1 002 platser, byggd där Maria saluhall låg. "
                      "Folkoperan har huserat här sedan 1984."),
                    [("sv:Folkoperan", ["Därför sjunger man alltid på svenska", "den ombyggda biografen Ricardo",
                                        "Hornsgatan 72 i Stockholm, som invigdes 1928",
                                        "en av Stockholms största biografer med 1 002 sittplatser",
                                        "på platsen för den tidigare Maria saluhall", "huserar sedan 1984"])]),
             find("lm:Lilla Blecktornet",
                  T("Not far from Hammarby sjö, a two-storey stone house from 1787 stands in the east of the park named "
                    "after it. Find this old malmgård.",
                    "Inte långt från Hammarby sjö står ett stenhus i två våningar från 1787 i den östra delen av parken "
                    "som bär dess namn. Hitta den gamla malmgården."),
                  [T("A health spring stood here in the late 1600s; a doctor said its water was a fine gathering of "
                     "frogs, leeches and other worms.",
                     "Här låg på 1600-talets slut en hälsobrunn; en läkare sa att vattnet var ett vackert samkväm för "
                     "grodor, iglar och andra maskar.")],
                  T("Lilla Blecktornet, built for the manufacturer Niklas Sjöberg. The name may come from a tower where "
                    "cloth was bleached.",
                    "Lilla Blecktornet, byggt åt fabrikören Niklas Sjöberg. Namnet kan komma från ett torn där man "
                    "blekte tyger."),
                  [("sv:Lilla Blecktornet", ["Stenbyggnaden från 1787 ligger i Lilla Blecktornsparkens östra del",
                                             "tvåvåningars stenhus",
                                             "inte lång från Hammarby sjö som malmgård för fabrikören Niklas Sjöberg",
                                             "Södermalms surbrunn, en hälsobrunn",
                                             "varande ett vackert samkväm för grodor, iglar och andra maskar",
                                             "där man blekte tyger"])]),
             year("lm:Fasta paviljongen",
                  T("On Långholmen, this cell block of the old central prison had cells big enough for a carpenter's "
                    "bench. When was it finished?",
                    "På Långholmen hade den här cellbyggnaden i det gamla centralfängelset celler så stora att en "
                    "hyvelbänk rymdes. När blev den klar?"),
                  1915,
                  T("It was built from 1914 to 1915. From 1969 until the prison closed in 1975 it was the women's wing; "
                    "a preschool and a school use it now.",
                    "Den uppfördes 1914 till 1915. Från 1969 till nedläggningen 1975 var den kvinnoavdelningen; i dag "
                    "används den av en förskola och en grundskola."),
                  [("sv:Fasta paviljongen, Långholmen", ["Åren 1914 till 1915 uppfördes",
                                                         "en hyvelbänk rymdes i varje",
                                                         "Från 1969 till nedläggningen 1975 var den kvinnoavdelningen",
                                                         "används lokalerna av en förskola och en grundskola"])]),
         ]),

    dict(id="ostermalm", level=2,
         title=T("Östermalm and Gärdet", "Östermalm och Gärdet"),
         intro=T("Five buildings from Östermalmstorg to Hjorthagen: a food hall, a hospital, a museum of technology, "
                 "the county's tallest tower and a gasworks.",
                 "Fem byggnader från Östermalmstorg till Hjorthagen: en saluhall, ett sjukhus, ett tekniskt museum, "
                 "länets högsta torn och ett gasverk."),
         steps=[
             find("lm:Östermalms saluhall",
                  T("A brick cathedral of food on Östermalmstorg, with the winged hat of Hermes, the symbol of trade, "
                    "on its corner tower. Find it.",
                    "En tegelkatedral för mat vid Östermalmstorg, med den bevingade hermeshatten, handelns symbol, på "
                    "hörntornet. Hitta den."),
                  [T("Isak Gustaf Clason, who also drew Nordiska museet, designed it with Kasper Salin.",
                     "Isak Gustaf Clason, som också ritade Nordiska museet, ritade den med Kasper Salin.")],
                  T("Östermalms saluhall. It took only six months to build, and Oscar II was there when it opened on "
                    "30 November 1888.",
                    "Östermalms saluhall. Bygget tog bara sex månader, och Oscar II var på plats när den invigdes den "
                    "30 november 1888."),
                  [("sv:Östermalms saluhall", ["mot Östermalmstorg", "tegelkatedral",
                                               "den bevingade hermeshatten (symbolen för handeln)",
                                               "Isak Gustaf Clason och Kasper Salin",
                                               "invigdes den 30 november 1888 i kung Oscar II:s närvaro",
                                               "bara sex månader förflutit från byggstart till avslut"]),
                   ("sv:Nordiska museet", ["efter ritningar av arkitekt Isak Gustaf Clason"])]),
             choice("lm:KTH-huset",
                    T("This eight-storey building on Norra Djurgården, built on an American model, now houses KTH's "
                      "management. What was it built as?",
                      "Den här byggnaden i åtta våningar på Norra Djurgården, byggd efter amerikansk förebild, inrymmer i "
                      "dag KTH:s ledning. Vad byggdes den som?"),
                    [T("A Red Cross hospital", "Ett sjukhus för Röda Korset"), T("A hotel", "Ett hotell"),
                     T("A telephone exchange", "En telefonstation")],
                    T("Röda Korsets sjukhus, drawn by Carl Westman. Prince Carl, chairman of the Swedish Red Cross for "
                      "almost 40 years, opened it on 5 September 1927.",
                      "Röda Korsets sjukhus, ritat av Carl Westman. Prins Carl, i närmare 40 år ordförande i Svenska Röda "
                      "Korset, invigde det den 5 september 1927."),
                    [("sv:Röda Korsets sjukhus", ["Sjukhuset har åtta våningar och byggdes efter amerikansk förebild",
                                                  "Norra Djurgården", "fick namnet KTH-huset och numera inrymmer "
                                                  "Tekniska högskolans ledning", "Arkitekt var Carl Westman",
                                                  "invigdes den 5 september 1927 av dess initiativtagare Prins Carl",
                                                  "närmare 40 år ordförande i Svenska Röda Korset"])]),
             year("lm:Tekniska museet",
                  T("Ragnar Hjorth drew Tekniska museet's main building on Gärdet in strict functionalism. When was it "
                    "finished?",
                    "Ragnar Hjorth ritade Tekniska museets huvudbyggnad på Gärdet i stram funktionalism. När stod den "
                    "klar?"),
                  1936,
                  T("In 1936: Prime Minister Per Albin Hansson was there when it opened on 18 May 1936. The museum's "
                    "model was the Deutsches Museum in Munich.",
                    "År 1936: statsminister Per Albin Hansson var på plats när den invigdes den 18 maj 1936. Museets "
                    "förebild var Deutsches Museum i München."),
                  [("sv:Tekniska museet", ["ritades av arkitekt Ragnar Hjorth och stod färdig 1936",
                                           "i stram funktionalism",
                                           "invigdes den 18 maj 1936 i närvaro av statsminister Per-Albin Hansson",
                                           "Förebilden var Deutsches Museum i München"])]),
             find("lm:Kaknästornet",
                  T("Stockholm County's tallest building is a 155-metre tower on Gärdet, the hub of Sweden's radio and "
                    "TV network. Find it.",
                    "Stockholms läns högsta byggnad är ett 155 meter högt torn på Gärdet, centrum i Sveriges radio- och "
                    "TV-nät. Hitta det."),
                  [T("The whole tower went up in 35 days.", "Hela byggnaden restes på 35 dygn.")],
                  T("Kaknästornet, opened on 12 May 1967 by Olof Palme, then minister of communications. In 2018 it was "
                    "announced that it would stay closed to the public.",
                    "Kaknästornet, invigt den 12 maj 1967 av dåvarande kommunikationsministern Olof Palme. År 2018 "
                    "aviserades att tornet stängs för allmänheten."),
                  [("sv:Kaknästornet", ["ett torn på Gärdet", "centrum i radio- och TV-nätet",
                                        "Tornet har en höjd av 155 meter", "Stockholms läns högsta byggnad",
                                        "Hela byggnaden restes på 35 dygn",
                                        "invigdes 12 maj 1967 av dåvarande kommunikationsminister Olof Palme",
                                        "permanent stängs för allmänheten aviserades på juldagen 2018"])]),
             year("lm:Värtagasverket",
                  T("Ferdinand Boberg, who also drew Mosebacke's water tower, designed the red-brick gasworks in "
                    "Hjorthagen. When did it first send gas into the network?",
                    "Ferdinand Boberg, som också ritade Mosebacke vattentorn, ritade det röda tegelgasverket i "
                    "Hjorthagen. När släppte det ut gas på nätet första gången?"),
                  1893,
                  T("On 6 November 1893, and Oscar II opened it officially on 25 November. It made town gas until it "
                    "closed in January 2011.",
                    "Den 6 november 1893, och Oscar II förrättade den officiella invigningen den 25 november. Det "
                    "levererade stadsgas fram till nedläggningen i januari 2011."),
                  [("sv:Värtagasverket", ["stadsdelen Hjorthagen", "ritades av arkitekt Ferdinand Boberg",
                                          "6 november 1893 kunde den väldiga anläggningens första fjärdedel tas i bruk",
                                          "officiella invigning den 25 november 1893 förrättades av kung Oscar II",
                                          "fram till nedläggningen i januari 2011"]),
                   ("sv:Mosebacke vattentorn", ["ritades av arkitekt Ferdinand Boberg"])]),
         ]),

    dict(id="soderort", level=3,
         title=T("South of the city", "Söderort"),
         intro=T("Five buildings in the southern suburbs: a giant sphere, a World Heritage crematorium, a white school, "
                 "a school from 1915 and a school by the lake.",
                 "Fem byggnader i Söderort: en jättelik sfär, ett krematorium som är världsarv, en vit skola, en skola "
                 "från 1915 och en skola vid sjön."),
         steps=[
             find("lm:Avicii Arena",
                  T("Until 2023, the world's largest spherical building stood in Johanneshov. Find it.",
                    "Fram till 2023 låg världens största sfäriska byggnad i Johanneshov. Hitta den."),
                  [T("It is the Sun in Sweden Solar System, a scale model of the solar system.",
                     "Den är solen i Sweden Solar System, en skalmodell av solsystemet.")],
                  T("Globen, since 2021 Avicii Arena, opened on 19 February 1989. Its architects had called their "
                    "design Prins Bertil Arena.",
                    "Globen, sedan 2021 Avicii Arena, invigd den 19 februari 1989. Arkitekterna hade kallat sitt förslag "
                    "Prins Bertil Arena."),
                  [("sv:Globen", ["sedan 2021 Avicii Arena", "Johanneshov",
                                  "var fram till 2023 världens största sfäriska byggnad",
                                  "Globen representerar solen", "Den invigdes den 19 februari 1989",
                                  "kallade de byggnaden för Prins Bertil Arena"])]),
             year("lm:Skogskrematoriet",
                  T("Gunnar Asplund's crematorium at Skogskyrkogården has been part of a World Heritage Site since 1994. "
                    "When was it inaugurated?",
                    "Gunnar Asplunds krematorium vid Skogskyrkogården är sedan 1994 en del av ett världsarv. När "
                    "invigdes det?"),
                  1940,
                  T("On 21 June 1940. Asplund died that October and was cremated here; his gravestone reads "
                    "\"His work lives\".",
                    "Den 21 juni 1940. Asplund dog i oktober samma år och kremerades här; hans epitafium lyder "
                    "\"Hans verk lever\"."),
                  [("sv:Skogskrematoriet", ["ritades 1935-1940 av Gunnar Asplund",
                                            "sedan 1994 upptagen som ett världsarv", "invigdes den 21 juni 1940",
                                            "Han dog i oktober samma år och kremerades här", "Hans verk lever"])]),
             find("lm:Enskedefältets skola",
                  T("On a hill in Enskedefältet stands a school from 1933 with smooth, light façades. For its colour it "
                    "was also called the White School. Find it.",
                    "På en kulle i Enskedefältet står en skola från 1933 med släta, ljusputsade fasader. För färgens "
                    "skull kallades den även Vita skolan. Hitta den."),
                  [T("Paul Hedqvist won the competition for it in 1932. It stands on Sockenvägen.",
                     "Paul Hedqvist vann tävlingen om den 1932. Den ligger vid Sockenvägen.")],
                  T("Enskedefältets skola, built for the fast-growing number of children in Enskedefältet's small "
                    "houses, the småstugor.",
                    "Enskedefältets skola, byggd för det snabbt växande barnantalet i Enskedefältets småstugor."),
                  [("sv:Enskedefältets skola", ["Sockenvägen 370", "Skolhuset uppfördes 1933 efter ritningar av "
                                                "arkitekt Paul Hedqvist",
                                                "Arkitektuppdraget gick 1932 efter en arkitekttävling till Paul "
                                                "Hedqvist", "släta ljusputsade fasader", "Vita skolan",
                                                "uppfördes på en kulle",
                                                "det snabbt växande barnantalet i Enskedefältets småstugor"])]),
             choice("lm:Långbrodalsskolan",
                    T("Georg A. Nilsson drew Långbrodalsskolan, built 1914–1915. Which two schools were built at the "
                      "same time to the same drawings?",
                      "Georg A. Nilsson ritade Långbrodalsskolan, uppförd 1914–1915. Vilka två skolor byggdes samtidigt "
                      "efter samma ritningar?"),
                    [T("Örbyskolan and Enskede skola", "Örbyskolan och Enskede skola"),
                     T("Eriksdalsskolan and Ålstensskolan", "Eriksdalsskolan och Ålstensskolan"),
                     T("Olovslundsskolan and Bällstalundsskolan", "Olovslundsskolan och Bällstalundsskolan")],
                    T("Örbyskolan and Enskede skola. The brick house echoes the plain stone houses of the 1600s; its new "
                      "wing won Årets Stockholmsbyggnad, Stockholm's building of the year, in 2018.",
                      "Örbyskolan och Enskede skola. Tegelhuset anknyter till 1600-talets enkla stenhus; tillbyggnaden "
                      "vann Årets Stockholmsbyggnad 2018."),
                    [("sv:Långbrodalsskolan", ["Skolan uppfördes 1914–1915 och ritades av Georg A. Nilsson",
                                               "Örbyskolan och Enskede skola byggdes samtidigt efter samma ritningar",
                                               "anknyter till 1600-talets enkla stenhus",
                                               "Tillbyggnaden utnämndes till vinnaren i arkitekturtävlingen Årets "
                                               "Stockholmsbyggnad 2018"])]),
             find("lm:Hägerstenshamnens skola",
                  T("Find the school by Klubbfjärden whose two buildings step down towards Lake Mälaren. Its entrance "
                    "window is made to look like an aquarium.",
                    "Hitta skolan vid Klubbfjärden vars två huskroppar trappar ner mot Mälaren. Fönstret vid entrén "
                    "påminner om ett akvarium."),
                  [T("The school that stood here before, a wooden building, burned down in April 2015.",
                     "Skolan som låg här förut, en träbyggnad, brann ner i april 2015.")],
                  T("Hägerstenshamnens skola, opened for the autumn term of 2017. In the window, Carin Ellberg let "
                    "plants, animals and things from Mälaren in.",
                    "Hägerstenshamnens skola, invigd till höstterminen 2017. I fönstret lät Carin Ellberg växter, djur "
                    "och föremål ur Mälaren ta sig in."),
                  [("sv:Hägerstenshamnens skola", ["trappar ner mot Klubbfjärden, Mälaren", "påminner om ett akvarium",
                                                   "Skolhuset var en träbyggnad", "brann ner i april 2015",
                                                   "Till höstterminen 2017 invigdes den nya Hägerstenshamnens skola",
                                                   "gestaltades av konstnären Carin Ellberg",
                                                   "Hon lät växter, djur och föremål ur Mälaren ta sig in"])]),
         ]),

    dict(id="bromma", level=3,
         title=T("Out in Bromma", "Ute i Bromma"),
         intro=T("Five buildings in the west: a bell tower from the 1690s and four schools, from Stockholm's oldest to "
                 "one built just after the war.",
                 "Fem byggnader i väster: en klockstapel från 1690-talet och fyra skolor, från Stockholms äldsta till "
                 "en som byggdes strax efter kriget."),
         steps=[
             find("lm:Klockstapeln, Bromma kyrka",
                  T("On Kråsberget, 200 metres north-east of Bromma kyrka, stands an open bell frame with no walls. "
                    "Find it.",
                    "På Kråsberget, 200 meter nordost om Bromma kyrka, står en öppen klockstapel utan väggar. Hitta "
                    "den."),
                  [T("It was probably moved up the hill so the bells could be heard far and wide among Bromma's farmers.",
                     "Den flyttades troligen upp på berget för att ljudet skulle höras vida omkring bland "
                     "brommabönderna.")],
                  T("Bromma kyrka's bell tower, built 1692–1695. The builder finished only after he was threatened "
                    "with prison.",
                    "Bromma kyrkas klockstapel, byggd 1692–1695. Byggmästaren avslutade arbetet först när han hotades med "
                    "fängelse."),
                  [("sv:Klockstapeln, Bromma kyrka", ["200 meter nordost om Bromma kyrka", "Kråsberget",
                                                      "inte panelklädd och har inte väggar",
                                                      "ljudet skulle höras vida omkring bland brommabönderna",
                                                      "byggdes 1692-1695",
                                                      "avslutade inte arbetet i Bromma förrän han hotades med "
                                                      "fängelse"])]),
             year("lm:Bromma kyrkskola",
                  T("Next to Bromma kyrka stands Stockholm's smallest and oldest school. When was it built?",
                    "Bredvid Bromma kyrka ligger Stockholms minsta och äldsta skola. När byggdes den?"),
                  1864,
                  T("In 1864: the parish meeting decided to build it in 1862. Two classes still have their lessons here.",
                    "År 1864: sockenstämman beslöt att bygga den 1862. Två klasser undervisas fortfarande här."),
                  [("sv:Bromma kyrkskola", ["byggdes 1864 och är Stockholms minsta och äldsta skola",
                                            "strax bredvid Bromma kyrka",
                                            "Vid sockenstämman 1862 togs ett beslut om att bygga en ny skola",
                                            "används fortfarande för undervisning av två klassavdelningar"])]),
             choice("lm:Ålstensskolan",
                    T("Two royal children went to middle school at Ålstensskolan. Who?",
                      "Två kungliga barn gick mellanstadiet i Ålstensskolan. Vilka?"),
                    [T("Crown Princess Victoria and Prince Carl Philip", "Kronprinsessan Victoria och prins Carl Philip"),
                     T("Prince Bertil and Prince Carl", "Prins Bertil och prins Carl"),
                     T("Princess Astrid and Prince Eugen", "Prinsessan Astrid och prins Eugen")],
                    T("Victoria, from 1987 to 1990, and Carl Philip, from 1989 to 1992. Ture Ryberg drew the school; "
                      "from its hall you see straight down Ålstensgatan to Lake Mälaren.",
                      "Victoria, 1987–1990, och Carl Philip, 1989–1992. Ture Ryberg ritade skolan; från aulan ser man "
                      "Ålstensgatan i rät linje ända ner till Mälaren."),
                    [("sv:Ålstensskolan", ["Kronprinsessan Victoria gick mellanstadiet i Ålstensskolan från "
                                           "höstterminen 1987 till vårterminen 1990",
                                           "Prins Carl Philip gick mellanstadiet här från höstterminen 1989 till "
                                           "vårterminen 1992", "efter ritningar av arkitekt Ture Ryberg",
                                           "kan se hela Ålstensgatan i rät linje ända ner till Mälarens vatten"])]),
             find("lm:Olovslundsskolan",
                  T("A functionalist school whose main building curves along Åkerslundsgatan with a radius of 150 "
                    "metres. Find it.",
                    "En funktionalistisk skola vars huvudbyggnad är svängd utmed Åkerslundsgatan med en radie på 150 "
                    "meter. Hitta den."),
                  [T("Paul Hedqvist, who also drew Enskedefältets skola, was its architect.",
                     "Paul Hedqvist, som också ritade Enskedefältets skola, var dess arkitekt.")],
                  T("Olovslundsskolan, opened on 31 August 1931.", "Olovslundsskolan, invigd den 31 augusti 1931."),
                  [("sv:Olovslundsskolan", ["Skolan invigdes den 31 augusti 1931 med Paul Hedqvist som arkitekt",
                                            "Skolan byggdes i funktionalistisk stil",
                                            "svängd utmed Åkerslundsgatan med en radie på 150 meter"]),
                   ("sv:Enskedefältets skola", ["efter ritningar av arkitekt Paul Hedqvist"])]),
             year("lm:Södra Ängby skola",
                  T("Ture Ryberg also drew this functionalist school on Blackebergsvägen, near Islandstorget. When was "
                    "it built?",
                    "Ture Ryberg ritade också den här funktionalistiska skolan på Blackebergsvägen, nära Islandstorget. "
                    "När byggdes den?"),
                  1946,
                  T("In 1946, and it took its first classes the same year. Since 1944 trams had run to Islandstorget; "
                    "the metro took over the same tracks in 1952.",
                    "År 1946, och samma år tog den emot sina första klasser. Sedan 1944 gick spårvagnar till "
                    "Islandstorget; 1952 började tunnelbanan köra på samma spår."),
                  [("sv:Södra Ängby skola", ["Blackebergsvägen nära Islandstorget",
                                             "uppfördes 1946 efter ritningar av arkitekten Ture Ryberg i "
                                             "funktionalismens anda",
                                             "Samma år var skolan färdig att ta emot sina första klasser",
                                             "från 1 oktober 1944 gick Ängbybanans linje 11",
                                             "trafikerades som spårväg till 1952, då tunnelbanan började köra på "
                                             "samma spår"])]),
         ]),
]
