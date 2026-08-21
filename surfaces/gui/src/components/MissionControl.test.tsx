/** Mission control: renders live rows, hides when quiet, stop + jump actions. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getActivity = vi.fn();
const interruptSession = vi.fn((_id: string) => Promise.resolve({ ok: true }));

vi.mock("../api", () => ({
  getActivity: () => getActivity(),
  interruptSession: (id: string) => interruptSession(id),
  connectEvents: () => () => undefined,
}));

import { MissionControl } from "./MissionControl";

const noop = () => undefined;

describe("MissionControl", () => {
  beforeEach(() => {
    getActivity.mockReset();
    interruptSession.mockClear();
  });
  afterEach(cleanup);

  it("renders nothing while the app is quiet", async () => {
    getActivity.mockResolvedValue({ busy: false, items: [] });
    render(
      <MissionControl onSelectSession={noop} onOpenAutomation={noop} onOpenInbox={noop} />,
    );
    await waitFor(() => expect(getActivity).toHaveBeenCalled());
    expect(screen.queryByTestId("mission-control")).toBeNull();
  });

  it("lists running work and jumps to a session on click", async () => {
    const onSelectSession = vi.fn();
    getActivity.mockResolvedValue({
      busy: true,
      items: [
        {
          kind: "session",
          id: "s1",
          title: "Draft the syllabus",
          workspace: "/ws",
          agent: "cowork",
          started_at: Date.now() / 1000 - 90,
        },
        { kind: "automation", id: "a1", title: "Morning digest", started_at: 1 },
        { kind: "approval", id: "i1", title: "Wants to send an email", session_id: "s2" },
      ],
    });
    render(
      <MissionControl
        onSelectSession={onSelectSession}
        onOpenAutomation={noop}
        onOpenInbox={noop}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("mission-control")).toBeTruthy());
    expect(screen.getByText("Draft the syllabus")).toBeTruthy();
    expect(screen.getByText("Morning digest")).toBeTruthy();
    expect(screen.getByText("Wants to send an email")).toBeTruthy();
    fireEvent.click(screen.getByTestId("mc-session"));
    expect(onSelectSession).toHaveBeenCalledWith("s1", "/ws", "cowork");
  });

  it("stop button interrupts without opening the session", async () => {
    const onSelectSession = vi.fn();
    getActivity.mockResolvedValue({
      busy: true,
      items: [
        {
          kind: "session",
          id: "s1",
          title: "Long task",
          workspace: "/ws",
          agent: "cowork",
          started_at: 0,
        },
      ],
    });
    render(
      <MissionControl
        onSelectSession={onSelectSession}
        onOpenAutomation={noop}
        onOpenInbox={noop}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("mission-control")).toBeTruthy());
    const stop = screen.getByRole("button", { name: "Stop this session" });
    expect(stop.tagName).toBe("BUTTON");
    stop.focus();
    expect(document.activeElement).toBe(stop);
    fireEvent.click(stop);
    expect(interruptSession).toHaveBeenCalledWith("s1");
    expect(onSelectSession).not.toHaveBeenCalled();
  });

  it("approval rows route to the inbox", async () => {
    const onOpenInbox = vi.fn();
    getActivity.mockResolvedValue({
      busy: false,
      items: [{ kind: "approval", id: "i1", title: "Needs your OK", session_id: "s1" }],
    });
    render(
      <MissionControl onSelectSession={noop} onOpenAutomation={noop} onOpenInbox={onOpenInbox} />,
    );
    await waitFor(() => expect(screen.getByTestId("mc-approval")).toBeTruthy());
    fireEvent.click(screen.getByTestId("mc-approval"));
    expect(onOpenInbox).toHaveBeenCalled();
  });
});
