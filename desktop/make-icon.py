"""Draw the code-defined molecular Jarvis application icon."""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

root=Path(__file__).parent
size=512
image=Image.new('RGBA',(size,size),(3,11,16,255))
draw=ImageDraw.Draw(image)
points=[]
for i in range(65):
    y=1-2*(i+.5)/65
    radius=math.sqrt(1-y*y)
    angle=i*math.pi*(3-math.sqrt(5))
    x,z=math.cos(angle)*radius,math.sin(angle)*radius
    points.append((x,y,z))
glow=Image.new('RGBA',image.size)
gd=ImageDraw.Draw(glow)
for i,(x,y,z) in enumerate(points):
    neighbors=sorted((sum((a-b)**2 for a,b in zip((x,y,z),q)),j) for j,q in enumerate(points) if j!=i)[:4]
    for _,j in neighbors:
        q=points[j]
        alpha=int(75+(z+q[2]+2)*32)
        gd.line((256+x*185,256+y*185,256+q[0]*185,256+q[1]*185),fill=(31,197,224,alpha),width=2)
for x,y,z in points:
    r=2+2*(z+1)/2
    gd.ellipse((256+x*185-r,256+y*185-r,256+x*185+r,256+y*185+r),fill=(128,241,255,int(100+75*(z+1))))
image=Image.alpha_composite(image,glow.filter(ImageFilter.GaussianBlur(6)))
image=Image.alpha_composite(image,glow)
draw=ImageDraw.Draw(image)
draw.arc((38,38,474,474),12,148,fill='#48cbe0',width=3)
draw.arc((38,38,474,474),192,328,fill='#48cbe0',width=3)
image.save(root/'icon.png')
image.save(root/'icon.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
