import csv
import requests
from rapidfuzz import process


# (fuzzy-)match string local auth names to gov.uk register codes
class CodeMatcher:

    def __init__(self):
        councils = self.get_data()
        councils = [c for c in councils if not c['end-date']]

        self.long_names = [c['official-name'] for c in councils]
        self.short_names = [c['name'] for c in councils]
        self.long_name_to_code = {
            c['official-name']: c['local-authority-eng'] for c in councils
        }
        self.short_name_to_code = {
            c['name']: c['local-authority-eng'] for c in councils
        }

    def get_data(self):
        r = requests.get(
            'https://www.registers.service.gov.uk/registers/local-authority-eng/download-csv'
        )

        csv_reader = csv.DictReader(r.text.splitlines())
        return list(csv_reader)

    def get_register_code(self, name):
        if 'council' in name.lower():
            match, score = process.extractOne(name, self.long_names)
            code = self.long_name_to_code[match]
        else:
            match, score = process.extractOne(name, self.short_names)
            code = self.short_name_to_code[match]

        if score > 95:
            # close enough
            return (code, match, score)

        return (None, match, score)
