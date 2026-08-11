// Friendly labels for the classifier's inference methods (paper_class.methods_used). KEEP IN SYNC
// with inference_method_tags in bayesify/api/papers_store.py — the Archive facet uses the same
// mapping, so a paper's report chips and Archive tags show identical labels. Shared by the report
// header and the Analyzing screen's progressive classification chips so both render from one source.
export const METHOD_LABELS: Record<string, string> = {
  mcmc: "MCMC",
  hmc_nuts: "MCMC (HMC/NUTS)",
  variational: "Variational inference",
  sbi: "SBI",
  smc: "SMC",
  abc: "ABC",
  laplace_inla: "Laplace/INLA",
  map: "MAP",
  em: "EM",
  exact_analytic: "Analytic",
};

export const methodChips = (methodsUsed?: string[]): string[] => (methodsUsed ?? []).map((m) => METHOD_LABELS[m] ?? m);
