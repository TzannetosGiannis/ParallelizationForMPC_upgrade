import json
import matplotlib.pyplot as plt
from fpdf import FPDF


MOTION = 'MOTION'
MP_SPDZ = 'MP-SPDZ'
metric_time = 'time'
metric_commRounds = 'commRounds'
metric_dataSent = 'dataSent'
execution_list = [
    (MOTION,metric_time),
    (MOTION,metric_dataSent),
    (MOTION,metric_commRounds),
    (MP_SPDZ,metric_time),
    (MP_SPDZ,metric_dataSent),
    (MP_SPDZ,metric_commRounds)
]
for backend,metric in execution_list:
    # Load JSON data from file
    if backend == 'MOTION':
        with open(f"./Cost_Tables/{backend}/{metric}.json", "r") as file:
            data = json.load(file)['32']
    else:
        with open(f"./Cost_Tables/{backend}/semi/{metric}.json", "r") as file:
            data = json.load(file)['32']

    # Create PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    counter=0
    for section in data.keys():
        
        zi_data = data.get(section, {})

        if section.startswith("zic_"):
            zi_data = {
                section:data.get(section, {})
            }
        keys = sorted(list(zi_data.keys()))
        # Create a figure for saving as PDF
        fig, axes = plt.subplots(1, len(keys), figsize=(10, 5))
        fig.suptitle(f"operation={section} backend={backend} costType={metric}", fontsize=14, fontweight='bold')  # Add title to figure

        for i in range(len(keys)):
            values = zi_data[keys[i]]
            x_axis_data = list(map(int, values.keys()))
            y_axis_data = list(values.values())
            obj = axes if len(keys) == 1 else axes[i]
            obj.plot(x_axis_data, y_axis_data, marker='o', linestyle='-', color='b')
            if not section.startswith("zic"):
                obj.set_title(f"Protocol {keys[i]}")
            else:
                obj.set_title(f"Convertion from {keys[i].split('_')[1].replace('2',' to ')}")
            obj.set_xlabel("Vector size")
            obj.set_ylabel("Cost per element")
        
        # Save the plot as an image
        plot_filename = f"./Cost_Tables/images/{section}_{backend}_{metric}_plot.png"
        plt.tight_layout()
        plt.savefig(plot_filename)
        plt.close()

        if counter % 3 == 0:
            pdf.add_page()
        pdf.image(plot_filename, x=10, y=pdf.get_y(), w=180)  # Insert image at correct position
        pdf.ln(95)  # Adjust spacing to prevent overlap

        counter+=1

    # Save PDF
    pdf_filename = f"./Cost_Tables/{backend}_{metric}_plot.pdf"
    pdf.output(pdf_filename)

    print(f"Plot saved as {pdf_filename}")

