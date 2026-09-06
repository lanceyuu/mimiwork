// Add-model family dropdown for the cloud-account providers: the family choice folds
// into the model id (`bedrock:claude/…`, `vertex:openweight/…`); plain providers keep
// the bare add-model row.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ModelChecklist } from "./ModelChecklist";

vi.mock("../api", () => ({
  addModel: vi.fn(async (id: string) => ({ ok: true, models: [id], model: id })),
  removeModel: vi.fn(async () => ({ ok: true, models: [], model: "" })),
  setDefaultModel: vi.fn(async () => ({ ok: true })),
  getSettings: vi.fn(async () => ({ models: [], model: "" })),
}));

import { addModel } from "../api";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const KNOWN = ["openai", "anthropic", "bedrock", "vertex", "openrouter"];

function renderList(provider: string) {
  return render(
    <ModelChecklist
      provider={provider}
      knownProviders={KNOWN}
      suggested={[]}
      curated={[]}
      defaultModel=""
      onChanged={() => {}}
    />,
  );
}

function addTyped(id: string) {
  fireEvent.change(screen.getByPlaceholderText("Add another model…"), {
    target: { value: id },
  });
  fireEvent.click(screen.getByText("Add"));
}

describe("ModelChecklist add-model family dropdown", () => {
  it("folds the selected vertex family into the id", async () => {
    renderList("vertex");
    fireEvent.change(screen.getByTestId("mlist-family"), {
      target: { value: "openweight" },
    });
    addTyped("meta/llama-4-maverick-17b-128e-instruct-maas");
    expect(addModel).toHaveBeenCalledWith(
      "vertex:openweight/meta/llama-4-maverick-17b-128e-instruct-maas",
    );
  });

  it("defaults bedrock to the Claude family and keeps a typed family verbatim", async () => {
    renderList("bedrock");
    addTyped("anthropic.claude-sonnet-4-6-v1:0");
    expect(addModel).toHaveBeenCalledWith(
      "bedrock:claude/anthropic.claude-sonnet-4-6-v1:0",
    );
    addTyped("other/amazon.nova-2-pro-v1:0");
    expect(addModel).toHaveBeenLastCalledWith("bedrock:other/amazon.nova-2-pro-v1:0");
  });

  it("shows no family dropdown for plain providers", async () => {
    renderList("openrouter");
    expect(screen.queryByTestId("mlist-family")).toBeNull();
    addTyped("z-ai/glm-5.2");
    expect(addModel).toHaveBeenCalledWith("openrouter:z-ai/glm-5.2");
  });
});

// A live catalog (OpenRouter's free models) is a shortlist, not a wall: the first six
// plus anything ticked; "Show all" opens the rest; the add box autocompletes every id.
describe("ModelChecklist shortlist for long live catalogs", () => {
  const live = Array.from({ length: 17 }, (_, i) => `lab/model-${i}:free`);
  it("folds a long suggestion list and unfolds on Show all", () => {
    render(
      <ModelChecklist
        provider="openrouter"
        knownProviders={KNOWN}
        suggested={live}
        curated={["openrouter:lab/model-15:free"]}
        defaultModel=""
        onChanged={() => {}}
      />,
    );
    const names = () => screen.getAllByTitle(/^openrouter:/).map((el) => el.getAttribute("title"));
    expect(names()).toHaveLength(7); // six best-first + the ticked one from further down
    expect(names()).toContain("openrouter:lab/model-15:free");
    expect(document.querySelectorAll("datalist option")).toHaveLength(17);
    fireEvent.click(screen.getByTestId("mlist-more"));
    expect(names()).toHaveLength(17);
    expect(screen.getByTestId("mlist-more").textContent).toBe("Show fewer");
  });
  it("leaves short lists alone", () => {
    render(
      <ModelChecklist provider="openrouter" knownProviders={KNOWN} suggested={live.slice(0, 5)} curated={[]} defaultModel="" onChanged={() => {}} />,
    );
    expect(screen.getAllByTitle(/^openrouter:/)).toHaveLength(5);
    expect(screen.queryByTestId("mlist-more")).toBeNull();
  });
});
