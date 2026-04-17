
from utility_compress_pdf import compress_pdf
import os

directory = "C:/Users/jdhou/OneDrive/Documents/Arts/Reading/Calibre/Peter C. Verhoef, Edwin Kooge, Natas/Creating Value with Data Analytics i (58)"


files = [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]

for i, file in enumerate(files):
    input_path = directory+"/"+str(file)
    output_path = directory+"/"+str(file)[:-4] + "_compressed.pdf"
    compress_pdf(input_path, output_path)
    print(input_path)
    #print(output_name)