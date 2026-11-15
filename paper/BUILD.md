# L74 paper build notes

In-repo directory layout:
`paper/`

- `paper/main.tex`: LaTeX source for the L74 technical report.
- `paper/refs.bib`: BibTeX bibliography references.
- `paper/numbers.json`: Source of truth for all experimental numbers.
- `paper/numbers.tex`: LaTeX macros generated from `numbers.json`.
- `paper/make_figures.py`: Optional script generating `figures/*.{pdf,png}` and `numbers.tex`.
- `paper/figures/`: Pre-rendered figures included in `main.tex`.
- `paper/latexmkrc`: Latexmk configuration for the build pipeline.
- `paper/main.pdf`: Pre-built technical report artifact.

## Official acceptance command

From the `paper/` directory:

```bash
cd paper
latexmk -pdf main.tex
```

## Toolchain & Build Environment

The committed PDF (`paper/main.pdf`) was built on a Linux box using the following toolchain:

- `latexmk` 4.89, installed from CTAN as `/home/box/.local/bin/latexmk`
  (https://mirrors.ctan.org/support/latexmk/latexmk.pl), because
  `apt-get` against Debian Trixie returned HTTP 500 / unsigned repositories
  and could not install `texlive` / `latexmk`.
- Engine wrapper `/home/box/.local/bin/tectonic-pdflatex`, which forwards
  the run to Tectonic 0.17.0 at `/home/box/.local/bin/tectonic`.
- Local `latexmkrc` setting `$pdf_mode = 1` and `$bibtex_use = 0`
  (Tectonic performs its own bibliography pass).

Equivalent direct engine call (not the acceptance command):

```bash
tectonic --keep-logs --keep-intermediates --print main.tex
```

> **Note on Windows builds:**
> This Windows PC may not have that toolchain. A Windows rebuild is not
> required for acceptance; `paper/main.pdf` is committed directly.

## Regenerating Figures & Macros

Regenerating figures and number macros is optional and requires `matplotlib` and `numpy` (which are not runtime dependencies of Skeptic):

```bash
cd paper
python make_figures.py
```

`make_figures.py` reads only `paper/numbers.json` and writes `paper/figures/*.pdf`,
`paper/figures/*.png`, and `paper/numbers.tex`.

All experimental statistics in `main.tex` are inserted via `\Lxx...` macros from `numbers.tex`,
which is generated only from `numbers.json`.
