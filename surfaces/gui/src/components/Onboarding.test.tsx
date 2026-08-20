/** Onboarding step 3 ("give Mimi her first task"): folder gate + starter cards. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const chooseFolder = vi.fn();
vi.mock("../tauri", () => ({
  chooseFolder: () => chooseFolder(),
}));

import { Onboarding } from "./Onboarding";

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      // /v1/providers returns a bare ARRAY (useProviderSetup .find()s on it).
      json: async () => (String(url).includes("/v1/providers") ? [] : {}),
    }) as unknown as Response),
  );
}

describe("Onboarding first-task step", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    chooseFolder.mockReset();
  });

  it("skip on the model step lands straight in the app (no starter)", async () => {
    const onDone = vi.fn();
    stubFetch();
    render(<Onboarding onDone={onDone} />);
    fireEvent.click(screen.getByText("Skip setup"));
    fireEvent.click(await screen.findByText("skip anyway"));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(undefined, undefined));
  });

  it("starter cards gate on the folder + write permission, then hand over the grant", async () => {
    const onDone = vi.fn();
    stubFetch();
    render(<Onboarding onDone={onDone} __startStep={2} />);

    expect((screen.getByTestId("ob-starter-summarize") as HTMLButtonElement).disabled).toBe(true);

    chooseFolder.mockResolvedValue("/Users/me/Course");
    fireEvent.click(screen.getByTestId("ob-pick-folder"));
    await waitFor(() =>
      expect(
        (screen.getByTestId("ob-starter-summarize") as HTMLButtonElement).disabled,
      ).toBe(false),
    );
    // Write-needing starter stays gated until the permission is granted.
    expect((screen.getByTestId("ob-starter-tidy") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("ob-folder-writable"));
    expect((screen.getByTestId("ob-starter-tidy") as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(screen.getByTestId("ob-starter-summarize"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const [next, starter] = onDone.mock.calls[0];
    expect(next).toBe("work");
    expect(starter).toEqual({
      workspace: "/Users/me/Course",
      writable: true,
      prompt: expect.stringContaining("overview"),
    });
  });

  it("blank-session and automation doors survive as footer links", async () => {
    const onDone = vi.fn();
    stubFetch();
    render(<Onboarding onDone={onDone} __startStep={2} />);
    fireEvent.click(screen.getByTestId("ob-start"));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("work", undefined));
  });
});
