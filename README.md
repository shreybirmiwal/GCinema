# GCinema - Deepmind X YC hackathon 26

## Hackathon prompt
Use the following tools to use the full multimodal stack - native audio, real-time video, and high-fidelity image generation - to build something that wasn't possible six months ago

- Gemini 3.1: The latest iteration with expanded long-context reasoning and native agentic vision.
- Lyria: DeepMind’s specialized model for high-fidelity music and transformational audio.
- NanoBanana 2: The new state-of-the-art for image composition, character consistency, and sub-pixel text rendering.

## Strategy
 - 4 differnet products so we can max different sandboxed claude code instances 
 - Terminal CLI with colors and streaming output (visually cool and technically complex points from judges)
 - Pick idea that is inherently demo'able and visual

Thoughts
 - hmm is the move to only do one product? 

## GCinema
1. **GColour**
 Watch old, black and white silent films in a modern dub with color and music

 - INPUT: A short mp4 film of a old, no audio, black and white film
 - GENERATION:
    Video
    a) Use Gemini 3.1 to watch the entire film and reason on the general premise of the film
    b) Use Gemini 3.1 to understand each object / colors of each object in the scene
    b) Break video into frames
    c) (Parallelize) Use NanoBanana 2 to generate each frame a colorized version, using context from steps A,B as context
        ci) We may need to take a few random frames then stitch together using Veo or a video model to generate the 'in between' if we cannot generate many picture files

        https://www.youtube.com/watch?v=mpjEyBKSfJQ
        1. Gemini take this clip and split into scenes of AT MAX 8 seconds. Eacn scene should be ONE camera shot, meaning not a change in scene. Each scene describe what is happening and generate a color pallet, ie ["Scene: Man running down cobblestone street", "Blue coat, cobblestone", "00:00 - 00:02"]
        2. Get start and end frame for each MAX 8 second clip
        3. Generate colored keyframes "colorize this picture, maintaining this color pallet [pallet from gemini], similar style and pallet to this [previous image]]"
        4. Veo3: Using start and end frame for each MAX 8 second clip, generate the video that does [scene description "man running"] with 
        
        feedback
        1. Gemini 3.1 is great at reasoning, but asking it to give you precise millisecond timestamps for shot changes solely via vision can be jittery.
        The Fix: Use a dedicated, lightweight library like PySceneDetect first. It’s a specialized tool that finds camera cuts instantly.
        The Workflow: PySceneDetect finds the cuts → Gemini 3.1 describes each cut and assigns the color palette. This ensures your "at max 8 seconds" rule is strictly enforced by code, not just "guessed" by the LLM.

        2. The Correction: Instead of giving Veo 3 a "Start and End frame," it's usually more stable to give it a Start Frame (the colorized image from NanoBanana 2) and a Text Prompt.

    d) Piece each frame together, save mp4 file

    Audio
    a) Use Gemini 3.1 to understand the context of realistic audio / sound track of the video
    b) Use Gemini Lyria to generate the sound track using prompt
    *D) We can have audio from either the Veo video or use a different system to create audio of voices / sfx / ai narration
    c) Save generated mp3 audio file to file system

    Piece together
    a) Using pymovie connect the video and audio, extend mp3 audio to length of video
    b) Save final mp4 file to file system

 - OUTPUT
    CLI
    a) The CLI will allow the user to select between 3 pre selected videos or upload their own clip

    While generating
    a) CLI tool only! Have a terminal prompt that splits into 2 (left=video, right=audio)
    b) Have a pinned "To-Do" like claude to-do visable on the left (a-d) and right (a-c)
    c) Have each stage (a-d) be a different highlighted color in terminal for visability

    When Done
    a) Once CLI is completed, open up a local host that simply pulls local files and displays the videos (VERY SIMPLE AND BARE BONES is key, the terminal stream be the cool part) 
    b) Judges remember before vs after. So your UI should show: Original clip  |  Restored clip. Side by side. Even better if the transformation slides across the video.

2. **GVisualize**
replaces characters with ur friends faces or
replaces objects in the back with ads (ie coca cola) in movie based on user preferences

3. **GAlternate**
reasons over a clip using 3.1
determines alternative endings
generates a comic book of alternative endings

4. **GScene**
3D world model reconstruction of a movie scene
gemini reasons on video
extract scene pics
nano banana generates many angles of pics
world model generates 3d world
you can play it