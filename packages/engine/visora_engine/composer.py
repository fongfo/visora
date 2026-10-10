from pathlib import Path
import textwrap

from .media import prepare_font, run_ffmpeg
from .schemas import TimelineSchema


def compose(timeline: TimelineSchema, mixed_audio: Path, output: Path):
    # Revalidate mutable model trees at the render boundary.
    timeline = TimelineSchema.model_validate(timeline.model_dump())
    output = output.resolve()
    work = output.parent / (output.stem + "-render")
    prepare_font(work)
    args, filters = [], []
    for i, clip in enumerate(timeline.tracks.video_clips):
        args += ["-i", str(Path(clip.source_url).resolve())]
        filters.append(f"[{i}:v]trim=start={clip.trim_start}:duration={clip.duration},"
                       f"setpts=PTS-STARTPTS,fps=30,scale=1080:1920,setsar=1,"
                       f"format=yuv420p,settb=AVTB[v{i}]")
    args += ["-i", str(mixed_audio.resolve())]
    current = "v0"
    for i in range(1, 4):
        start = timeline.tracks.video_clips[i].timeline_start
        filters.append(f"[{current}][v{i}]xfade=transition=dissolve:duration=0.3:offset={start}[x{i}]")
        current = f"x{i}"
    for i, subtitle in enumerate(timeline.tracks.subtitles):
        # File-based text avoids treating content as filter expressions.
        (work / f"subtitle-{i}.txt").write_text(textwrap.fill(subtitle.text, width=42), encoding="utf-8")
        filters.append(f"[{current}]drawtext=fontfile=font.ttf:textfile=subtitle-{i}.txt:expansion=none:"
                       f"fontsize=40:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=16:"
                       f"x=(w-tw)/2:y=h-240:enable='between(t,{subtitle.start_time},{subtitle.end_time})'[s{i}]")
        current = f"s{i}"
    for i, overlay in enumerate(timeline.tracks.overlays):
        args += ["-loop", "1", "-i", str(Path(overlay.asset_url).resolve())]
        filters.append(f"[{current}][{5+i}:v]overlay=x={overlay.x}:y={overlay.y}:"
                       f"enable='between(t,{overlay.start_time},{overlay.start_time + overlay.duration})'[o{i}]")
        current = f"o{i}"
    filters.append(f"[{current}]format=yuv420p[out]")
    args += ["-filter_complex_threads", "1", "-filter_complex", ";".join(filters),
             "-map", "[out]", "-map", "4:a", "-t", str(timeline.duration),
             "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
             "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(output)]
    run_ffmpeg(args, work)
