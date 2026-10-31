"""Render the conceptual workflow overview; run from any directory (requires Pillow)."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BG, INK, EDGE, PURPLE, GOLD = "#f5f7fb", "#18345a", "#60748c", "#7a58aa", "#bd7a13"
img = Image.new("RGB", (1600, 1190), BG)
d = ImageDraw.Draw(img)
def font(size, bold=False):
    candidates = [Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf"),
                  Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")]
    for path in candidates:
        if path.exists(): return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)
LABEL, SMALL, TITLE = font(29), font(23), font(43, True)
d.text((60, 24), "SilverFile | Workflow overview", fill=INK, font=TITLE)
d.text((60, 84), "Six agents, parallel extraction, and resumable staff review", fill="#526580", font=SMALL)
nodes = {
    "start": (660,150,960,230,"Session start"),
    "intake": (80,410,400,510,"Intake"),
    "orch": (660,410,960,520,"Orchestrator"),
    "extract": (1200,150,1520,240,"Parallel Extraction"),
    "aggregate": (1200,295,1520,375,"Aggregate records"),
    "rules": (1200,435,1520,535,"Rules"),
    "compute": (80,690,400,790,"Computation"),
    "review": (660,790,960,890,"Review"),
    "staff": (1200,690,1520,790,"Staff review"),
    "draft": (80,180,400,270,"Draft ready"),
}
def arrow(points, color=EDGE):
    d.line(points, fill=color, width=4, joint="curve")
    a,b=points[-2:]; angle=math.atan2(b[1]-a[1],b[0]-a[0])
    d.polygon([b,(b[0]-17*math.cos(angle-.43),b[1]-17*math.sin(angle-.43)),
                (b[0]-17*math.cos(angle+.43),b[1]-17*math.sin(angle+.43))],fill=color)
arrow([(810,230),(810,410)])
arrow([(400,445),(660,445)])
arrow([(660,485),(400,485)])
arrow([(930,410),(930,265),(1100,265),(1100,195),(1200,195)])
arrow([(1360,240),(1360,295)])
arrow([(1200,335),(1040,335),(1040,425),(960,425)])
arrow([(960,465),(1200,465)])
arrow([(1200,505),(960,505)])
arrow([(660,500),(400,720)])
arrow([(400,765),(705,520)])
arrow([(755,520),(755,790)])
arrow([(850,790),(850,520)], PURPLE)
arrow([(960,520),(1200,720)], GOLD)
arrow([(1200,765),(920,520)], GOLD)
arrow([(660,425),(540,320),(400,240)])
d.text((425,205),"Review passed",fill=EDGE,font=SMALL)
for key,(x1,y1,x2,y2,label) in nodes.items():
    fill=INK if key=="orch" else "#ffffff"
    d.rounded_rectangle((x1,y1,x2,y2),radius=16,fill=fill,outline=GOLD if key=="staff" else "#aebdd0",width=2)
    box=d.textbbox((0,0),label,font=LABEL)
    d.text(((x1+x2-(box[2]-box[0]))/2,(y1+y2-(box[3]-box[1]))/2-box[1]),label,
           fill="white" if key=="orch" else INK,font=LABEL)
notes=["Review limit: 3 revisions",
       "Loop guard: 3 repeated handoffs in the last 10, without progress",
       "Fallback: 80 handoffs without progress",
       "SQLite checkpoints preserve sessions across restarts.",
       "Production: draft_ready | Routing demo (--demo): scaffold_complete"]
for i,text in enumerate(notes): d.text((65,965+i*37),text,fill="#526580",font=SMALL)
d.text((65,1160),"Conceptual routing overview; worker dispatch details are grouped.",fill="#526580",font=font(19))
img.save(ROOT/"docs/graph.png")
