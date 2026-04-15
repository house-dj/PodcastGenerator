import re
import json

# --- Report Content and Target Schema (Included for self-contained demonstration) ---

REPORT_CONTENT = """
Carolingians and the Frankish Realm, 750 to 987

Introduction: Setting the Stage for a New Dynasty
The Frankish realm in the early 8th century operated under a nominal Merovingian monarchy, a dynasty which had, by this period, largely receded into symbolic impotence. These kings, often characterized as *rois fainéants* or 'do-nothing kings,' possessed little actual authority beyond their ceremonial functions. Their once formidable power had eroded, leaving them detached from the day-to-day administration and military command of the kingdom. Real power had steadily consolidated in the hands of the mayors of the palace, hereditary administrators who governed the kingdom’s various divisions—Austrasia, Neustria, and Burgundy. This shift marked a profound transformation in Frankish governance, as the Merovingians retained the ancient, sacred lineage of kingship, while the mayors controlled the military, the treasury, and the patronage networks essential for effective rule.

Among these powerful mayoral families, the Pippinids, who would later be known as the Carolingians, emerged as the preeminent force. Beginning with Pippin II and cemented by his illegitimate son Charles Martel, their control over the Frankish military and their consistent victories against external threats, such as the Muslim advance at Tours in 732, further enhanced their prestige and popular support throughout the Frankish lands. By the mid-8th century, the authority of the Merovingian kings was virtually nonexistent, setting the stage for a dynastic coup.

Pippin III: The Papal Alliance and the End of the Merovingians
Pippin the Younger, son of Charles Martel, made the final, decisive move to claim the Frankish throne. In 751, with the critical sanction of the Papacy, he deposed the last Merovingian king, Childeric III, and had himself anointed as King of the Franks. This act was revolutionary: it replaced the ancient, semi-divine lineage of the Merovingians with a new concept of kingship legitimized by the Church. The Pope's willingness to grant this sanction was politically motivated, as Rome urgently needed a powerful protector against the aggressive Lombards in Italy. Pippin responded by conducting military campaigns against the Lombards, which resulted in the donation of lands to the Papacy—the 'Donation of Pippin'—laying the territorial foundation for the Papal States and cementing the deep, reciprocal alliance between the Carolingians and the Church.

Charlemagne: King and Emperor
The consolidation and expansion of the Frankish realm reached its zenith under Pippin's son, Charles, later known as Charlemagne (Charles the Great), who reigned from 768 to 814. Charlemagne’s reign was defined by relentless military conquest, expanding Frankish control across modern-day France, Germany, and Italy. His most significant political act occurred on Christmas Day in 800 CE, when Pope Leo III crowned him Emperor of the Romans in Rome. This event symbolically resurrected the Western Roman Empire and formalized the Carolingian claim to imperial authority, though it caused considerable diplomatic tension with the Byzantine Empire in the East. Charlemagne’s ambition was not merely military; he viewed himself as the protector of the Christian West, responsible for both its political security and its moral and spiritual welfare.

Administration and Government
Managing this vast, diverse empire required novel administrative methods. Charlemagne's government was highly centralized around his mobile court. To ensure regional accountability, he appointed *missi dominici* ('envoys of the lord ruler'), pairs of officials (usually a lay lord and a bishop or abbot) who traveled throughout the empire to inspect local administration, enforce imperial decrees (*capitularies*), and hear judicial appeals. Local administration relied on counts, who governed territories and commanded local armies, and the marcher lords (margraves), who governed the volatile border regions (*marches*). The entire system was bound together by oaths of loyalty and the King's personal, charismatic authority.

The Carolingian Renaissance
Charlemagne fostered a period of intellectual and cultural revival known as the Carolingian Renaissance. Based primarily at the palace school in Aachen, led by scholars like Alcuin of York, this movement aimed to standardize literacy, Latin, and Christian practice across the realm. Key achievements included the creation of a clear, standardized script (Carolingian Minuscule), which vastly improved readability, and a renewed effort to correct and copy ancient Latin texts, thus preserving much of classical learning that would have otherwise been lost. This intellectual fervor was fundamentally a tool of imperial and ecclesiastical reform, ensuring that administrators and clergy were educated enough to run the empire and correctly interpret religious texts.

Dynastic Fragmentation and the Treaty of Verdun
The tradition of dividing the Frankish kingdom among a ruler's sons proved fatal to Charlemagne's unified empire. After the death of his only surviving son, Louis the Pious, in 840, civil war erupted among Louis's three sons: Lothair, Louis the German, and Charles the Bald. The conflict was formally resolved by the Treaty of Verdun in 843. This treaty partitioned the empire into three distinct political entities: West Francia (Charles the Bald), East Francia (Louis the German), and Middle Francia (Lothair, which stretched from the North Sea to Italy). While the treaty attempted to resolve the fraternal dispute, it inadvertently created the territorial precursors for modern-day France and Germany, and permanently dissolved the concept of a single, unified Carolingian Empire.

The Second Wave of Invasions
The fragmentation caused by the Treaty of Verdun occurred just as Western Europe faced new, severe external threats. Between the mid-9th and mid-10th centuries, Vikings attacked from the north, sailing up rivers to plunder settlements; Magyars, or Hungarians, raided from the east; and Saracens (Muslims) conducted raids from the south, seizing control of coastal areas and threatening Italy. The now-divided Carolingian kingdoms proved unable to mount a coordinated defense. The inability of kings to protect their subjects led to the rise of local military strongmen (counts, dukes, and margraves), who built fortifications and commanded local loyalties. This devolution of power contributed significantly to the feudalization of the realm and the eventual displacement of the Carolingian line by regional powers that had steadily consolidated their authority in the absence of a strong, centralizing hand.

Conclusion: The Enduring Shadow of the Carolingian Age
The Carolingian age, spanning over two centuries, left an indelible mark on the political, cultural, and ecclesiastical identity of medieval Europe. Its core achievements began with the articulation of a new imperial ideal under Charlemagne, which integrated Roman traditions with a sacralized Christian kingship, deeply legitimized by papal anointing. This period also initiated significant administrative and ecclesiastical reforms, standardizing Christian practice and fostering an intellectual revival that preserved classical learning, establishing foundations for future European thought and education. However, the inherent challenges of maintaining such a vast realm, compounded by dynastic fragmentation and persistent external pressures from Vikings, Magyars, and Saracens, ultimately led to the empire's dissolution into separate kingdoms. Yet, this very breakdown into distinct political entities, notably West and East Francia, laid the territorial groundwork for future European nations. The lasting shadow of the Carolingians rests in their enduring influence on the concept of imperial authority, the model of sacred monarchy, and the institutional frameworks for church governance, shaping the self-perception and organizational structures of medieval polities long after the dynasty’s direct rule had faded.
"""

# --- End of Included Content ---

def extract_outline(report_text):
    """
    Reads a report text and dynamically extracts the main sections based on common
    heading patterns (capitalized lines preceded by a blank line), and formats the
    output into a JSON outline following the provided schema structure.

    The function identifies:
    1. The main report title from the very first line.
    2. The main sections using dynamic header detection.
    3. The purpose/summary from the first sentence(s) of each section's content.

    Args:
        report_text (str): The raw text content of the report.
        target_schema (dict): A sample dictionary defining the desired output structure.

    Returns:
        dict: A dictionary containing the extracted outline structure.
    """
    cleaned_text = report_text.strip()

    # 1. Extract the main title from the first line
    main_title_match = re.search(r'^[^\n]+', cleaned_text)
    main_title = main_title_match.group(0).strip() if main_title_match else "Extracted Report Outline"

    # 2. Dynamically identify all main headings in the document.
    # Pattern: Finds a line that is preceded by at least two newlines (or start of string),
    # starts with an uppercase letter, and captures the whole line as the header.
    # This assumes major headings are separated by empty lines and start with a capital.
    heading_pattern = re.compile(r'(^[A-Z][a-z][^\n]+\n)', re.MULTILINE)

    section_data = []

    # Add the main title as the first data point to correctly determine the content boundary
    # for the Introduction section.
    section_data.append({'header': main_title, 'start': 0})

    # Find all potential headings and their start indices
    for match in heading_pattern.finditer(cleaned_text):
        header_text = match.group(1).strip()
        start_index = match.start(1)  # Start index of the captured heading text

        # Filter out the main title itself if the regex caught it, or short lines
        if header_text != main_title and 1 < len(header_text.split()) < 20:  # critical to get lines 20 words or less as the
            # regex is picking up the body text too
            section_data.append({'header': header_text, 'start': start_index})

    # Sort the sections by their appearance order
    section_data.sort(key=lambda x: x['start'])

    extracted_sections = []

    # Iterate through the sections, starting from the first *actual* section (index 1 in section_data)
    for i in range(1, len(section_data)):
        data = section_data[i]
        header_text = data['header']

        # Determine the content start index (immediately after the header line ends)
        # Find the end of the header's line
        header_line_end = data['start'] + cleaned_text[data['start']:].find('\n')
        content_start_index = header_line_end + 1

        # Determine the content end index (the start of the next header)
        if i + 1 < len(section_data):
            end_index = section_data[i + 1]['start']
        else:
            # If this is the last section, its content runs to the end of the document
            end_index = len(cleaned_text)

        section_content = cleaned_text[content_start_index:end_index].strip()
        section_snippet = section_content[:150]

        extracted_sections.append({
            "title": header_text,
            "content_snippet": section_snippet
        })

    # 3. Format the final output to strictly match the target schema structure
    schema_matched_output = {
        "title": main_title,
        "sections": []
    }

    # Re-process the extracted_sections to add Roman numerals
    for idx, section in enumerate(extracted_sections):
        # We need to map 0-based index to 1-based Roman numeral (I, II, III, ...)
        # We use a dictionary for safety, but can extend it if necessary
        section_number_roman = {
            0: "I", 1: "II", 2: "III", 3: "IV", 4: "V", 5: "VI", 6: "VII", 7: "VIII", 8: "IX", 9: "X"
        }.get(idx, str(idx + 1))

        final_title = f"{section_number_roman}. {section['title']}"

        schema_matched_output["sections"].append({
            "title": final_title,
            "content snippet": section['content_snippet']
        })

    return schema_matched_output


# --- Execution ---
"""
# Call the function to extract the outline
extracted_outline = extract_outline(REPORT_CONTENT)

# Print the final JSON structure for the user
print(json.dumps(extracted_outline, indent=2))
"""