#!/usr/bin/env bash
# Download the open-access sources of the Phase-1 deep research into research/sources/pdfs/
# (gitignored — we do not commit papers; paywalled ones are listed at the end with links).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p pdfs

fetch () { # fetch <output-name> <url>
  local out="pdfs/$1" url="$2"
  if [[ -s "$out" ]]; then echo "✓ (cached) $1"; return; fi
  echo "↓ $1"
  curl -fsSL --retry 3 -o "$out" "$url" || { echo "  ✗ failed: $url" >&2; rm -f "$out"; }
}

# --- arXiv (redistribution-safe author versions) ---
fetch gelman2020-bayesian-workflow.pdf        "https://arxiv.org/pdf/2011.01808"
fetch schad2021-principled-workflow-cogsci.pdf "https://arxiv.org/pdf/1904.12765"
fetch schad2022-bayes-factor-workflow.pdf     "https://arxiv.org/pdf/2103.08744"
fetch vehtari2021-improved-rhat.pdf           "https://arxiv.org/pdf/1903.08008"
fetch talts2018-sbc.pdf                       "https://arxiv.org/pdf/1804.06788"
fetch gabry2019-visualization.pdf             "https://arxiv.org/pdf/1709.01449"
fetch vehtari2017-psis-loo-waic.pdf           "https://arxiv.org/pdf/1507.04544"
fetch modrak2023-sbc-checking.pdf             "https://arxiv.org/pdf/2211.02383"
fetch riha2024-multiverse-filtering.pdf       "https://arxiv.org/pdf/2404.01688"

# --- open-access publisher PDFs ---
fetch kruschke2021-barg.pdf                   "https://www.nature.com/articles/s41562-021-01177-7.pdf"

# --- HTML-native sources (saved as .html) ---
fetch betancourt-principled-bayesian-workflow.html "https://betanalpha.github.io/assets/case_studies/principled_bayesian_workflow.html"

echo
echo "Not downloadable here (read online; see the corresponding .md notes for details):"
echo "  - Depaoli & van de Schoot 2017 (WAMBS) — APA paywall: https://doi.org/10.1037/met0000065"
echo "  - WAMBS-v2 tutorial — OA at Routledge/T&F: https://doi.org/10.4324/9780429273872-4"
echo "  - van de Schoot et al. 2021 primer — https://doi.org/10.1038/s43586-020-00001-2"
echo "  - Kelter 2024 (BASIS) — https://doi.org/10.1002/bimj.202200095"
echo "  - Nicenboim et al. textbook — https://bruno.nicenboim.me/bayescogsci/"
echo "  - Stan docs — https://mc-stan.org/learn-stan/diagnostics-warnings.html ; https://mc-stan.org/loo/reference/pareto-k-diagnostic.html"
echo "  - Gelman blog post — https://statmodeling.stat.columbia.edu/2020/11/10/bayesian-workflow/"
echo
echo "Done. PDFs in research/sources/pdfs/ (gitignored)."
