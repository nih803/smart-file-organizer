import os
import shutil

folder = "test_folder"
files = os.listdir(folder)
categories = {
    "Images": [".jpg", ".jpeg", ".png"],
    "PDFs": [".pdf"],
    "Music": [".mp3"],
    "Videos": [".mp4"],
    "Documents": [".docx", ".txt"],
    "Others": []
}
for i in files:
    if os.path.isdir(os.path.join(folder, i)):
        continue
    name, extension = os.path.splitext(i)
    found=False

    for category, extensions in categories.items():
        if extension.lower() in extensions:
           category_folder = os.path.join(folder, category)
           os.makedirs(category_folder, exist_ok=True)
           source = os.path.join(folder, i)
           destination = os.path.join(category_folder, i)
           shutil.move(source, destination)
           found=True
           break

        if not found:
            category_folder = os.path.join(folder, "Others")
            os.makedirs(category_folder, exist_ok=True)

            source = os.path.join(folder, i)
            destination = os.path.join(category_folder, i)

            shutil.move(source, destination)
