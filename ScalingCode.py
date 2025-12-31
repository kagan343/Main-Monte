# Code for scaling just radius of blade profiles
import os

# Set folder path here
folder = r"C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Scaling Code"
os.chdir(folder)

names_list = [
    "hub.curve",
    "profile.curve",
    "shroud.curve"
]

# Set scale factor here, scaled diameter or x variable only
scale = 0.5

for input_name in names_list:
    input_path = os.path.join(folder, input_name)
    output_path = os.path.join(folder, f"scaled_{input_name}")

    with open(input_path, "r") as f:
        lines = f.readlines()

    with open(output_path, "w") as f:
        for line in lines:
            parts = line.split()

            if len(parts) == 3:
                try:
                    x = float(parts[0]) * scale # X = radial position
                    y = float(parts[1]) # 
                    z = float(parts[2]) # Z = axial position

                    f.write(f"{x:.6f} {y:.6f} {z:.6f}\n")
                except ValueError:
                    f.write(line)
            else:
                f.write(line)

    print(f"Saved {output_path}\n")

print("All files scaled")
