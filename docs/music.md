# Music downloads

`ytm 'URL'` saves high-quality VBR MP3 audio, metadata, and cover art in the
current directory. Quote URLs, especially those containing `&` or `?`. Multiple
URLs can be passed together. Run `ytm --help` for all options.

```sh
ytm -o ~/Music 'https://www.youtube.com/playlist?list=...'
ytm --dry-run --items 1-5 'https://www.youtube.com/playlist?list=...'
ytm --single 'https://www.youtube.com/watch?v=...&list=...'
ytm -f opus -o ~/Music 'https://www.youtube.com/watch?v=...'
```

Playlists use a folder named after the playlist and numbered filenames. Single
videos stay directly in the destination. Playlist numbers distinguish repeated titles;
filenames preserve Unicode and sanitize embedded path separators. `--flat`
puts everything directly in the destination. `--items` selects playlist positions.
Video links that also contain a playlist download the entire playlist unless
`--single` is supplied.

`-f mp3` is the default; `m4a` and `opus` select other output formats. `-f best`
keeps the source audio codec, avoiding lossy re-encoding. Converting to MP3 cannot
improve the quality of the original source.

Completed downloads are recorded in `DESTINATION/.ytm/archive-FORMAT.txt`, so
repeat runs can pick up newly added playlist entries. History is separate for
each destination and format. Preserve the `.ytm` folder when moving a collection.
The archive tracks source IDs, not file existence: after removing files or
changing layouts, use `--no-archive` to fetch missing tracks. That option bypasses
history reads and writes. Existing audio is not redownloaded, but yt-dlp may
refresh its metadata and cover art when history is bypassed. Normal archive-based
repeat runs leave completed files untouched.
Tracks shared by different playlists within one destination/format are downloaded
only once by default; use `--no-archive` if each playlist needs its own copy.

Interrupted downloads resume. Unavailable entries do not stop a playlist, but
download or conversion failures still return an error. Missing fragments fail
the track rather than silently leaving gaps in the audio. yt-dlp's normal
configuration files are ignored so options there cannot override preview or
overwrite protection. Preview still contacts the source for metadata, respects
download history, and writes no downloads or history.

Requires `yt-dlp`, `ffmpeg`, and `ffprobe`, supplied by the common Linux profile.
The managed Bash and Zsh configurations expose the helper immediately in new
shells. The shell deployment also links `~/.local/bin/ytm` for other callers.
