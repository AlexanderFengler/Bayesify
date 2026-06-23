import CloseIcon from "@mui/icons-material/Close";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Typography,
} from "@mui/material";

// A titled dialog with a close affordance. Escape and backdrop-click both close (MUI defaults).
export function Modal({
  title,
  onClose,
  children,
  actions,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth scroll="paper">
      <DialogTitle sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", pr: 1 }}>
        <Typography component="span" variant="h6" sx={{ fontWeight: 700 }}>
          {title}
        </Typography>
        <IconButton aria-label="Close" onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>{children}</DialogContent>
      {actions && <DialogActions sx={{ px: 3, py: 2 }}>{actions}</DialogActions>}
    </Dialog>
  );
}

// The data-path explainer for one analysis mode — a coloured header strip over the prose.
function PrivacyMode({ mode, children }: { mode: "full" | "local"; children: React.ReactNode }) {
  const full = mode === "full";
  return (
    <Box sx={{ mt: 2 }}>
      <Box
        sx={{
          display: "inline-block",
          px: 1.25,
          py: 0.5,
          borderRadius: 1,
          mb: 1,
          fontSize: "0.8rem",
          fontWeight: 700,
          color: full ? "warning.main" : "success.main",
          bgcolor: full ? "warning.light" : "success.light",
        }}
      >
        {full ? "Full mode" : "Local-only mode"}
      </Box>
      <Typography variant="body2" color="text.secondary">
        {children}
      </Typography>
    </Box>
  );
}

// First-run disclosure + reusable privacy explainer (PRIVACY.md is the source of truth). States the
// outbound data path for each mode plainly, since authors upload unpublished manuscripts.
export function PrivacyModal({ onClose, firstRun }: { onClose: () => void; firstRun?: boolean }) {
  return (
    <Modal
      title={firstRun ? "Before you start" : "Privacy & data handling"}
      onClose={onClose}
      actions={
        firstRun ? (
          <Button variant="contained" disableElevation onClick={onClose}>
            Got it
          </Button>
        ) : undefined
      }
    >
      <Typography variant="body2" color="text.secondary">
        Bayesify is <strong>local-first</strong>: storage stays on this machine, there is no account,
        and no telemetry. There are two analysis modes, chosen per paper.
      </Typography>

      <PrivacyMode mode="full">
        To make per-step judgments, Bayesify sends the <strong>extracted text</strong> of your
        document to Anthropic (via your Claude subscription or API key). Nothing else leaves the
        machine — not the PDF file, not your identity, not the results. If a manuscript is
        confidential or embargoed, treat this as &ldquo;this text will be sent to a third-party API
        for processing&rdquo; and decide accordingly.
      </PrivacyMode>

      <PrivacyMode mode="local">
        <strong>Nothing leaves this machine.</strong> Local-only runs the parser and the
        deterministic detectors only — no LLM call, no text sent anywhere. It produces an evidence
        inventory (what was found and where), <strong>not a graded report</strong>: there are no
        coverage or quality scores, because scoring requires the model&rsquo;s judgment.
      </PrivacyMode>

      <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 2 }}>
        Submitting an identifier (arXiv/DOI/OpenAlex/URL) instead of a file fetches its open-access
        PDF &mdash; which reveals to that provider which paper you&rsquo;re looking up.
      </Typography>
    </Modal>
  );
}
