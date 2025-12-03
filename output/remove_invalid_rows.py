import csv
import sys

csv.field_size_limit(sys.maxsize)
input_file = "C:\\Users\\Giammaria\\Desktop\\output - Copia.csv"
output_file = "C:\\Users\\Giammaria\\Desktop\\output_clean.csv"

with open(input_file, "r", newline="", encoding="utf-8") as fin, \
     open(output_file, "w", newline="", encoding="utf-8") as fout:

    reader = csv.reader(fin)
    writer = csv.writer(fout)

    for row in reader:
        # Mantieni SOLO le righe che NON hanno 90 colonne
        if len(row) != 90:
            writer.writerow(row)

print("Fatto! Righe con 90 colonne rimosse e salvate in", output_file)