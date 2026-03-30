!pip install datalab-python-sdk

#DATALAB MARKER API
PDF_PATH = "KB_KB 탄탄대로 Biz_PDF로 파일저장_terms.pdf"
DATALAB_API_KEY = "YxM8pJWtSF_-IckATx6R5eQBbO4Lkkp5zQWeTc1y5n4"

import os
from datalab_sdk import DatalabClient, ConvertOptions
client = DatalabClient(api_key=DATALAB_API_KEY)

options = ConvertOptions(
    output_format="markdown",
    mode="balanced",
    paginate=False,
    disable_image_extraction= True,
    disable_image_captions= True,
    skip_cache= True
)

result = client.convert(PDF_PATH, options=options)

print("Conversion done.")
print(f"Cost: {result.cost_breakdown}")
print(f"Quality score: {result.parse_quality_score}")
print(f"Runtime: {result.runtime}")

# Save output
os.makedirs("./output/", exist_ok=True)
output_filename = os.path.splitext(os.path.basename(PDF_PATH))[0] + ".md"
with open(os.path.join("./output/", output_filename), "w", encoding="utf-8") as f:
    f.write(result.markdown)

print("Saving done.")
print(f"Output: ./output/{output_filename}")