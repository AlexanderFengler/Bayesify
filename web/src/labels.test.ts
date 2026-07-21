import { describe, expect, it } from "vitest";
import { methodChips } from "./labels";

describe("methodChips", () => {
  it("returns an empty array when methods are undefined", () => {
    expect(methodChips(undefined)).toEqual([]);
  });

  it("returns an empty array for no methods", () => {
    expect(methodChips([])).toEqual([]);
  });

  it("maps known method ids to their friendly labels", () => {
    expect(methodChips(["mcmc", "hmc_nuts", "variational"])).toEqual([
      "MCMC",
      "MCMC (HMC/NUTS)",
      "Variational inference",
    ]);
  });

  it("passes an unknown method id through unchanged", () => {
    expect(methodChips(["not_a_real_method"])).toEqual(["not_a_real_method"]);
  });

  it("maps knowns and passes unknowns through in one list", () => {
    expect(methodChips(["mcmc", "mystery"])).toEqual(["MCMC", "mystery"]);
  });
});
