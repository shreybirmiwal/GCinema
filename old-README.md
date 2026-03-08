# GCinema - Deepmind X YC hackathon 26

## Hackathon prompt
Use the following tools to use the full multimodal stack - native audio, real-time video, and high-fidelity image generation - to build something that wasn't possible six months ago

- Gemini 3.1: The latest iteration with expanded long-context reasoning and native agentic vision.
- Lyria: DeepMind’s specialized model for high-fidelity music and transformational audio.
- NanoBanana 2: The new state-of-the-art for image composition, character consistency, and sub-pixel text rendering.

---

# Strategy

- 4–5 different products so we can max different sandboxed Claude Code instances
- Terminal CLI with colors and streaming output (visually cool and technically complex points from judges)
- Pick ideas that are inherently **demo'able and visual**
- Show **before → after transformations**

Thoughts
- hmm is the move to only do one product?

---

# GCinema

---

# 1. GColour
Watch old, black and white silent films in a modern dub with color and music

## INPUT
A short mp4 film of an old, no audio, black and white film

## GENERATION

### Video

a) Use Gemini 3.1 to watch the entire film and reason on the general premise of the film  
b) Use Gemini 3.1 to understand each object / colors of each object in the scene  
c) Break video into frames  

d) (Parallelize) Use NanoBanana 2 to generate each frame a colorized version, using context from steps A,B

ci) We may need to take a few random frames then stitch together using Veo or a video model to generate the "in between" if we cannot generate many picture files

Example workflow:

https://www.youtube.com/watch?v=mpjEyBKSfJQ

1. Gemini takes the clip and splits it into scenes of AT MAX 8 seconds. Each scene should be ONE camera shot (no shot change).  
Each scene describes what is happening and generates a color palette.

Example

Scene: Man running down cobblestone street  
Palette: blue coat, grey cobblestone, cloudy sky  
Timestamp: 00:00 - 00:02

2. Get start and end frame for each MAX 8 second clip

3. Generate colored keyframes

"colorize this picture maintaining this palette [palette from Gemini]
similar style and palette to this [previous frame]"

4. Veo3 generation

Instead of giving Veo a start/end frame, it is more stable to give:

- Start Frame
- Scene Description

Example

Start frame: colorized image  
Prompt: "man running down cobblestone street in 1920s london"

### Improvements

Gemini can be jittery at millisecond shot detection.

Fix:

Use **PySceneDetect**

Workflow

PySceneDetect → find cuts  
Gemini → describe scene + assign palette

Ensures scenes follow the **8 second rule**.

---

### Audio

a) Use Gemini 3.1 to understand realistic audio context of the scene

Example

running footsteps  
crowd noise  
dramatic orchestral build

b) Use Gemini **Lyria** to generate soundtrack

c) Save generated mp3

Optional

- voice narration
- AI dialogue
- sound effects

---

### Piece Together

a) Using **pymovie**, combine video and audio  
b) Extend audio to match video length  
c) Save final mp4

---

## OUTPUT

### CLI

User selects

- 3 pre selected videos
- upload custom clip

---

### While Generating

Terminal splits into two sections

Left = Video pipeline  
Right = Audio pipeline

Pinned To-Do

Video  
a) Analyze film  
b) Detect scenes  
c) Colorize frames  
d) Generate video  

Audio  
a) Understand context  
b) Generate soundtrack  
c) Mix audio  

Each stage has a different color.

---

### When Done

Open a simple local host viewer

Show

Original clip | Restored clip

Optional

- sliding comparison bar

---

# 2. GVisualize

Replace characters with your friends' faces

OR

Replace background objects with ads based on user preferences

Example

Movie scene → Coke bottle appears on table

Uses

- Gemini scene reasoning
- NanoBanana image replacement

---

# 3. GAlternate

Generate alternate endings for movies.

Pipeline

1. Gemini 3.1 reasons over clip
2. Determines possible alternate endings
3. Generates comic book style panels

Example

Original ending → hero dies  
Alternate ending → hero escapes

NanoBanana generates the comic panels.

Output

"Alternate Ending Comic"

---

# 4. GScene

3D world model reconstruction of a movie scene.

### Pipeline

1. Gemini reasons over a movie clip
2. Extract key scene images
3. NanoBanana generates additional viewpoints
4. Build a **world model**
5. Generate a 3D scene
6. User can explore the scene

Example

Movie clip → reconstructed cafe → explore environment

---

# 5. GQuest

Turn the **physical world into a playable RPG environment**.

Camera sees your environment and transforms it into a fantasy world.

Example

table → stone altar  
door → dungeon gate  
lamp → torch  
couch → mountain ridge  

---

## INPUT

Live camera feed of a room or environment.

---

## GENERATION

### Scene Understanding

Gemini 3.1 analyzes the camera feed.

Example output

objects detected:
- table
- door
- lamp
- couch

Gemini also determines environment context

scene: living room

---

### World Model

Create a simple **scene graph**

Example

scene: living_room

objects:
table → altar  
door → dungeon_gate  
lamp → torch  
couch → mountain_ridge  

This becomes the **RPG world state**.

---

### Visual Generation

NanoBanana generates a transformed fantasy scene.

Prompt example

Convert this room into a dark fantasy dungeon  
stone altar where the table is  
torch lighting  
medieval RPG aesthetic

Output

Fantasy version of the environment.

---

### Audio Generation

Lyria generates an adaptive soundtrack.

Example prompts

fantasy dungeon ambience  
mysterious RPG soundtrack  
slow ambient music

Loop background music.

---

### Quest Generation

Gemini generates a quest based on scene objects.

Example

Quest: Retrieve the glowing crystal hidden on the altar.

---

## OUTPUT

User sees

Real world → RPG world transformation

Interactive elements

- quest text
- fantasy environment
- background music

---

## Data Flywheel Concept

Every scene creates data

Example

scene: kitchen  
objects: table, stove  
theme selected: alchemy lab  

Over time the system learns

kitchen → alchemy lab  
garage → goblin workshop  
office → wizard tower  

AI learns how environments map to fantasy worlds.

---

## Demo Flow

1. Point camera at room  
2. Gemini detects objects  
3. System prints world mapping

table → altar  
lamp → torch  
door → dungeon gate  

4. NanoBanana generates dungeon scene  
5. Lyria soundtrack starts  
6. Quest appears

Quest: Retrieve the crystal from the altar

---

# Summary

GCinema includes multiple multimodal AI tools:

- **GColour** – Restore silent films with color and soundtrack  
- **GVisualize** – Modify film scenes with objects or faces  
- **GAlternate** – Generate alternate movie endings  
- **GScene** – Reconstruct movie scenes into 3D environments  
- **GQuest** – Transform the physical world into an RPG game world

Each tool demonstrates a different capability of the multimodal stack:

- reasoning
- visual generation
- audio generation
- world modeling
- interactive environments





# prizes

best: yc interview
gemini: 

can use geminit o also dub films in diff languages



scenedetect>=0.6.7
opencv-python>=4.8
yt-dlp>=2024.1.0
google-genai>=1.0.0
