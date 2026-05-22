"""Shared curses-based UI components for Hermes CLI.

Used by `hermes tools` and `hermes skills` for interactive checklists.
Provides a curses multi-select with keyboard navigation, plus a
text-based numbered fallback for terminals without curses support.
"""
import sys
from typing import Callable, List, Optional, Set

from hermes_cli.colors import Colors, color


def flush_stdin() -> None:
    """Flush any stray bytes from the stdin input buffer.

    Must be called after ``curses.wrapper()`` (or any terminal-mode library
    like simple_term_menu) returns, **before** the next ``input()`` /
    ``getpass.getpass()`` call.  ``curses.endwin()`` restores the terminal
    but does NOT drain the OS input buffer — leftover escape-sequence bytes
    (from arrow keys, terminal mode-switch responses, or rapid keypresses)
    remain buffered and silently get consumed by the next ``input()`` call,
    corrupting user data (e.g. writing ``^[^[`` into .env files).

    On non-TTY stdin (piped, redirected) or Windows, this is a no-op.
    """
    try:
        if not sys.stdin.isatty():
            return
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def curses_checklist(
    title: str,
    items: List[str],
    selected: Set[int],
    *,
    cancel_returns: Set[int] | None = None,
    status_fn: Optional[Callable[[Set[int]], str]] = None,
) -> Set[int]:
    """Curses multi-select checklist. Returns set of selected indices.

    Args:
        title: Header line displayed above the checklist.
        items: Display labels for each row.
        selected: Indices that start checked (pre-selected).
        cancel_returns: Returned on ESC/q. Defaults to the original *selected*.
        status_fn: Optional callback ``f(chosen_indices) -> str`` whose return
            value is rendered on the bottom row of the terminal.  Use this for
            live aggregate info (e.g. estimated token counts).
    """
    if cancel_returns is None:
        cancel_returns = set(selected)

    # Safety: curses and input() both hang or spin when stdin is not a
    # terminal (e.g. subprocess pipe).  Return defaults immediately.
    if not sys.stdin.isatty():
        return cancel_returns

    try:
        import curses
        chosen = set(selected)
        result_holder: list = [None]

        def _draw(stdscr):
            curses.curs_set(0)
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, -1)
                curses.init_pair(2, curses.COLOR_YELLOW, -1)
                curses.init_pair(3, 8, -1)  # dim gray
            cursor = 0
            scroll_offset = 0

            while True:
                stdscr.clear()
                max_y, max_x = stdscr.getmaxyx()

                # Reserve bottom row for status bar when status_fn provided
                footer_rows = 1 if status_fn else 0

                # Header
                try:
                    hattr = curses.A_BOLD
                    if curses.has_colors():
                        hattr |= curses.color_pair(2)
                    stdscr.addnstr(0, 0, title, max_x - 1, hattr)
                    stdscr.addnstr(
                        1, 0,
                        "  ↑↓ navigate  SPACE toggle  ENTER confirm  ESC cancel",
                        max_x - 1, curses.A_DIM,
                    )
                except curses.error:
                    pass

                # Scrollable item list
                visible_rows = max_y - 3 - footer_rows
                if cursor < scroll_offset:
                    scroll_offset = cursor
                elif cursor >= scroll_offset + visible_rows:
                    scroll_offset = cursor - visible_rows + 1

                for draw_i, i in enumerate(
                    range(scroll_offset, min(len(items), scroll_offset + visible_rows))
                ):
                    y = draw_i + 3
                    if y >= max_y - 1 - footer_rows:
                        break
                    check = "✓" if i in chosen else " "
                    arrow = "→" if i == cursor else " "
                    line = f" {arrow} [{check}] {items[i]}"
                    attr = curses.A_NORMAL
                    if i == cursor:
                        attr = curses.A_BOLD
                        if curses.has_colors():
                            attr |= curses.color_pair(1)
                    try:
                        stdscr.addnstr(y, 0, line, max_x - 1, attr)
                    except curses.error:
                        pass

                # Status bar (bottom row, right-aligned)
                if status_fn:
                    try:
                        status_text = status_fn(chosen)
                        if status_text:
                            # Right-align on the bottom row
                            sx = max(0, max_x - len(status_text) - 1)
                            sattr = curses.A_DIM
                            if curses.has_colors():
                                sattr |= curses.color_pair(3)
                            stdscr.addnstr(max_y - 1, sx, status_text, max_x - sx - 1, sattr)
                    except curses.error:
                        pass

                stdscr.refresh()
                key = stdscr.getch()

                if key in {curses.KEY_UP, ord("k")}:
                    cursor = (cursor - 1) % len(items)
                elif key in {curses.KEY_DOWN, ord("j")}:
                    cursor = (cursor + 1) % len(items)
                elif key == ord(" "):
                    chosen.symmetric_difference_update({cursor})
                elif key in {curses.KEY_ENTER, 10, 13}:
                    result_holder[0] = set(chosen)
                    return
                elif key in {27, ord("q")}:
                    result_holder[0] = cancel_returns
                    return

        curses.wrapper(_draw)
        flush_stdin()
        return result_holder[0] if result_holder[0] is not None else cancel_returns

    except KeyboardInterrupt:
        return cancel_returns
    except Exception:
        return _numbered_fallback(title, items, selected, cancel_returns, status_fn)


def curses_radiolist(
    title: str,
    items: List[str],
    selected: int = 0,
    *,
    cancel_returns: int | None = None,
    description: str | None = None,
) -> int:
    """Curses single-select radio list. Returns the selected index.

    Args:
        title: Header line displayed above the list.
        items: Display labels for each row.
        selected: Index that starts selected (pre-selected).
        cancel_returns: Returned on ESC/q. Defaults to the original *selected*.
        description: Optional multi-line text shown between the title and
            the item list.  Useful for context that should survive the
            curses screen clear.
    """
    if cancel_returns is None:
        cancel_returns = selected

    if not sys.stdin.isatty():
        return cancel_returns

    desc_lines: list[str] = []
    if description:
        desc_lines = description.splitlines()

    try:
        import curses
        result_holder: list = [None]

        def _draw(stdscr):
            curses.curs_set(0)
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, -1)
                curses.init_pair(2, curses.COLOR_YELLOW, -1)
            cursor = selected
            scroll_offset = 0

            while True:
                stdscr.clear()
                max_y, max_x = stdscr.getmaxyx()

                row = 0

                # Header
                try:
                    hattr = curses.A_BOLD
                    if curses.has_colors():
                        hattr |= curses.color_pair(2)
                    stdscr.addnstr(row, 0, title, max_x - 1, hattr)
                    row += 1

                    # Description lines
                    for dline in desc_lines:
                        if row >= max_y - 1:
                            break
                        stdscr.addnstr(row, 0, dline, max_x - 1, curses.A_NORMAL)
                        row += 1

                    stdscr.addnstr(
                        row, 0,
                        "  \u2191\u2193 navigate  ENTER/SPACE select  ESC cancel",
                        max_x - 1, curses.A_DIM,
                    )
                    row += 1
                except curses.error:
                    pass

                # Scrollable item list
                items_start = row + 1
                visible_rows = max_y - items_start - 1
                if cursor < scroll_offset:
                    scroll_offset = cursor
                elif cursor >= scroll_offset + visible_rows:
                    scroll_offset = cursor - visible_rows + 1

                for draw_i, i in enumerate(
                    range(scroll_offset, min(len(items), scroll_offset + visible_rows))
                ):
                    y = draw_i + items_start
                    if y >= max_y - 1:
                        break
                    radio = "\u25cf" if i == selected else "\u25cb"
                    arrow = "\u2192" if i == cursor else " "
                    line = f" {arrow} ({radio}) {items[i]}"
                    attr = curses.A_NORMAL
                    if i == cursor:
                        attr = curses.A_BOLD
                        if curses.has_colors():
                            attr |= curses.color_pair(1)
                    try:
                        stdscr.addnstr(y, 0, line, max_x - 1, attr)
                    except curses.error:
                        pass

                stdscr.refresh()
                key = stdscr.getch()

                if key in {curses.KEY_UP, ord("k")}:
                    cursor = (cursor - 1) % len(items)
                elif key in {curses.KEY_DOWN, ord("j")}:
                    cursor = (cursor + 1) % len(items)
                elif key in {ord(" "), curses.KEY_ENTER, 10, 13}:
                    result_holder[0] = cursor
                    return
                elif key in {27, ord("q")}:
                    result_holder[0] = cancel_returns
                    return

        curses.wrapper(_draw)
        flush_stdin()
        return result_holder[0] if result_holder[0] is not None else cancel_returns

    except KeyboardInterrupt:
        return cancel_returns
    except Exception:
        return _radio_numbered_fallback(title, items, selected, cancel_returns)


def _radio_numbered_fallback(
    title: str,
    items: List[str],
    selected: int,
    cancel_returns: int,
) -> int:
    """Text-based numbered fallback for radio selection."""
    print(color(f"\n  {title}", Colors.YELLOW))
    print(color("  Select by number, Enter to confirm.\n", Colors.DIM))

    for i, label in enumerate(items):
        marker = color("(\u25cf)", Colors.GREEN) if i == selected else "(\u25cb)"
        print(f"  {marker} {i + 1:>2}. {label}")
    print()
    try:
        val = input(color(f"  Choice [default {selected + 1}]: ", Colors.DIM)).strip()
        if not val:
            return selected
        idx = int(val) - 1
        if 0 <= idx < len(items):
            return idx
        return selected
    except (ValueError, KeyboardInterrupt, EOFError):
        return cancel_returns


def curses_single_select(
    title: str,
    items: List[str],
    default_index: int = 0,
    *,
    cancel_label: str = "Cancel",
) -> int | None:
    """Curses single-select menu. Returns selected index or None on cancel.

    Works inside prompt_toolkit because curses.wrapper() restores the terminal
    safely, unlike simple_term_menu which conflicts with /dev/tty.
    """
    if not sys.stdin.isatty():
        return None

    try:
        import curses
        result_holder: list = [None]

        all_items = list(items) + [cancel_label]
        cancel_idx = len(items)

        def _draw(stdscr):
            curses.curs_set(0)
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, -1)
                curses.init_pair(2, curses.COLOR_YELLOW, -1)
            cursor = min(default_index, len(all_items) - 1)
            scroll_offset = 0

            while True:
                stdscr.clear()
                max_y, max_x = stdscr.getmaxyx()

                try:
                    hattr = curses.A_BOLD
                    if curses.has_colors():
                        hattr |= curses.color_pair(2)
                    stdscr.addnstr(0, 0, title, max_x - 1, hattr)
                    stdscr.addnstr(
                        1, 0,
                        "  ↑↓ navigate  ENTER confirm  ESC/q cancel",
                        max_x - 1, curses.A_DIM,
                    )
                except curses.error:
                    pass

                visible_rows = max_y - 3
                if cursor < scroll_offset:
                    scroll_offset = cursor
                elif cursor >= scroll_offset + visible_rows:
                    scroll_offset = cursor - visible_rows + 1

                for draw_i, i in enumerate(
                    range(scroll_offset, min(len(all_items), scroll_offset + visible_rows))
                ):
                    y = draw_i + 3
                    if y >= max_y - 1:
                        break
                    arrow = "→" if i == cursor else " "
                    line = f" {arrow} {all_items[i]}"
                    attr = curses.A_NORMAL
                    if i == cursor:
                        attr = curses.A_BOLD
                        if curses.has_colors():
                            attr |= curses.color_pair(1)
                    try:
                        stdscr.addnstr(y, 0, line, max_x - 1, attr)
                    except curses.error:
                        pass

                stdscr.refresh()
                key = stdscr.getch()

                if key in {curses.KEY_UP, ord("k")}:
                    cursor = (cursor - 1) % len(all_items)
                elif key in {curses.KEY_DOWN, ord("j")}:
                    cursor = (cursor + 1) % len(all_items)
                elif key in {curses.KEY_ENTER, 10, 13}:
                    result_holder[0] = cursor
                    return
                elif key in {27, ord("q")}:
                    result_holder[0] = None
                    return

        curses.wrapper(_draw)
        flush_stdin()
        if result_holder[0] is not None and result_holder[0] >= cancel_idx:
            return None
        return result_holder[0]

    except KeyboardInterrupt:
        return None
    except Exception:
        all_items = list(items) + [cancel_label]
        cancel_idx = len(items)
        return _numbered_single_fallback(title, all_items, cancel_idx)


def _numbered_single_fallback(
    title: str,
    items: List[str],
    cancel_idx: int,
) -> int | None:
    """Text-based numbered fallback for single-select."""
    print(f"\n  {title}\n")
    for i, label in enumerate(items, 1):
        print(f"  {i}. {label}")
    print()
    try:
        val = input(f"  Choice [1-{len(items)}]: ").strip()
        if not val:
            return None
        idx = int(val) - 1
        if 0 <= idx < len(items) and idx < cancel_idx:
            return idx
        if idx == cancel_idx:
            return None
    except (ValueError, KeyboardInterrupt, EOFError):
        pass
    return None


def _numbered_fallback(
    title: str,
    items: List[str],
    selected: Set[int],
    cancel_returns: Set[int],
    status_fn: Optional[Callable[[Set[int]], str]] = None,
) -> Set[int]:
    """Text-based toggle fallback for terminals without curses."""
    chosen = set(selected)
    print(color(f"\n  {title}", Colors.YELLOW))
    print(color("  Toggle by number, Enter to confirm.\n", Colors.DIM))

    while True:
        for i, label in enumerate(items):
            marker = color("[✓]", Colors.GREEN) if i in chosen else "[ ]"
            print(f"  {marker} {i + 1:>2}. {label}")
        if status_fn:
            status_text = status_fn(chosen)
            if status_text:
                print(color(f"\n  {status_text}", Colors.DIM))
        print()
        try:
            val = input(color("  Toggle # (or Enter to confirm): ", Colors.DIM)).strip()
            if not val:
                break
            idx = int(val) - 1
            if 0 <= idx < len(items):
                chosen.symmetric_difference_update({idx})
        except (ValueError, KeyboardInterrupt, EOFError):
            return cancel_returns
        print()

    return chosen


def curses_tree_checklist(
    title: str,
    groups: list,
    *,
    cancel_returns: set | None = None,
) -> set:
    """Curses collapsible tree with checkboxes for grouped model selection.

    Args:
        title: Header line.
        groups: List of group dicts:
            {name, expanded, items: [{id, label, checked}]}
        cancel_returns: Set of selected IDs to return on ESC/q.

    Returns:
        Set of selected item IDs. On cancel, returns cancel_returns.
    """
    if cancel_returns is None:
        cancel_returns = set()

    if not sys.stdin.isatty():
        return cancel_returns

    # Build flat row list for navigation
    # Each row: (type, group_idx, item_idx_or_None, visible)
    # type: "group" or "item"
    RowType = tuple

    def _build_flat() -> list:
        rows: list = []
        for gi, g in enumerate(groups):
            rows.append(("group", gi, None))
            if g.get("expanded", False):
                for ii in range(len(g.get("items", []))):
                    rows.append(("item", gi, ii))
        return rows

    # Track checked state (by item id)
    checked: set = set()
    for g in groups:
        for item in g.get("items", []):
            if item.get("checked"):
                checked.add(item["id"])

    try:
        import curses
        result_holder: list = [None]
        flat: list = _build_flat()
        cursor = 0

        def _draw(stdscr):
            nonlocal flat, cursor

            curses.curs_set(0)
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, -1)   # selected row
                curses.init_pair(2, curses.COLOR_YELLOW, -1)  # header
                curses.init_pair(3, 8, -1)                     # dim
                curses.init_pair(4, curses.COLOR_CYAN, -1)     # group header

            scroll_offset = 0

            while True:
                stdscr.clear()
                max_y, max_x = stdscr.getmaxyx()

                # Rebuild flat list on each iteration (groups may expand/collapse)
                flat = _build_flat()
                if cursor >= len(flat):
                    cursor = max(0, len(flat) - 1)

                # Header
                try:
                    hattr = curses.A_BOLD
                    if curses.has_colors():
                        hattr |= curses.color_pair(2)
                    stdscr.addnstr(0, 0, title, max_x - 1, hattr)
                    stdscr.addnstr(
                        1, 0,
                        "  ↑↓ nav  → expand  ← collapse  SPACE toggle  ENTER confirm  ESC cancel",
                        max_x - 1, curses.A_DIM,
                    )
                except curses.error:
                    pass

                # Selected count status
                try:
                    status = f"{len(checked)} model(s) selected"
                    sx = max(0, max_x - len(status) - 1)
                    sattr = curses.A_DIM
                    if curses.has_colors():
                        sattr |= curses.color_pair(3)
                    stdscr.addnstr(2, sx, status, max_x - sx - 1, sattr)
                except curses.error:
                    pass

                # Scrollable rows
                visible_rows = max_y - 4
                if cursor < scroll_offset:
                    scroll_offset = cursor
                elif cursor >= scroll_offset + visible_rows:
                    scroll_offset = cursor - visible_rows + 1

                for draw_i, ri in enumerate(
                    range(scroll_offset, min(len(flat), scroll_offset + visible_rows))
                ):
                    y = draw_i + 4
                    if y >= max_y - 1:
                        break

                    row = flat[ri]
                    row_type = row[0]
                    gi = row[1]

                    attr = curses.A_NORMAL
                    if ri == cursor:
                        attr = curses.A_BOLD
                        if curses.has_colors():
                            attr |= curses.color_pair(1)

                    if row_type == "group":
                        g = groups[gi]
                        expanded = g.get("expanded", False)
                        icon = "▼" if expanded else "▶"
                        count = len(g.get("items", []))
                        line = f" {icon} {g['name']} ({count} models)"
                        if ri == cursor:
                            # Use cyan for group cursor
                            if curses.has_colors():
                                attr = curses.A_BOLD | curses.color_pair(4)
                            else:
                                attr = curses.A_BOLD
                    else:
                        item_idx = row[2]
                        item = groups[gi]["items"][item_idx]
                        check = "✓" if item["id"] in checked else " "
                        line = f"    [{check}] {item['label']}"

                    try:
                        stdscr.addnstr(y, 0, line[:max_x - 1], max_x - 1, attr)
                    except curses.error:
                        pass

                stdscr.refresh()
                key = stdscr.getch()

                if key in {curses.KEY_UP, ord("k")}:
                    if len(flat) > 0:
                        cursor = (cursor - 1) % len(flat)
                elif key in {curses.KEY_DOWN, ord("j")}:
                    if len(flat) > 0:
                        cursor = (cursor + 1) % len(flat)
                elif key in {curses.KEY_RIGHT, ord("l")}:
                    # Expand group
                    row = flat[cursor] if cursor < len(flat) else None
                    if row and row[0] == "group":
                        groups[row[1]]["expanded"] = True
                elif key in {curses.KEY_LEFT, ord("h")}:
                    # Collapse group
                    row = flat[cursor] if cursor < len(flat) else None
                    if row and row[0] == "group":
                        groups[row[1]]["expanded"] = False
                    elif row and row[0] == "item":
                        # If on an item, jump to its parent group and collapse
                        parent_gi = row[1]
                        groups[parent_gi]["expanded"] = False
                        # Find parent group row index
                        flat = _build_flat()
                        for i, fr in enumerate(flat):
                            if fr[0] == "group" and fr[1] == parent_gi:
                                cursor = i
                                break
                elif key == ord(" "):
                    # Toggle: only for item rows
                    row = flat[cursor] if cursor < len(flat) else None
                    if row and row[0] == "item":
                        item = groups[row[1]]["items"][row[2]]
                        item_id = item["id"]
                        if item_id in checked:
                            checked.discard(item_id)
                        else:
                            checked.add(item_id)
                elif key in {curses.KEY_ENTER, 10, 13}:
                    result_holder[0] = set(checked)
                    return
                elif key in {27, ord("q")}:
                    result_holder[0] = cancel_returns
                    return

        curses.wrapper(_draw)
        flush_stdin()
        return result_holder[0] if result_holder[0] is not None else cancel_returns

    except KeyboardInterrupt:
        return cancel_returns
    except Exception:
        # Fallback: plain text numbered checklist
        return _tree_numbered_fallback(title, groups, checked, cancel_returns)


def _tree_numbered_fallback(
    title: str,
    groups: list,
    checked: set,
    cancel_returns: set,
) -> set:
    """Text-based fallback for the tree checklist."""
    from hermes_cli.colors import Colors, color

    # Build flat numbered list
    flat_items: list = []
    for g in groups:
        flat_items.append((None, f"[{g['name']}]"))
        for item in g.get("items", []):
            flat_items.append((item["id"], f"  {item['label']}"))

    print(color(f"\n  {title}", Colors.YELLOW))
    print(color("  Toggle by number, Enter to confirm.\n", Colors.DIM))

    while True:
        for i, (item_id, label) in enumerate(flat_items):
            if item_id is None:
                # Group header
                print(color(f"  {label}", Colors.CYAN))
            else:
                marker = color("[✓]", Colors.GREEN) if item_id in checked else "[ ]"
                print(f"  {marker} {i + 1:>3}. {label}")
        print()
        try:
            val = input(color("  Toggle # (or Enter to confirm): ", Colors.DIM)).strip()
            if not val:
                break
            idx = int(val) - 1
            if 0 <= idx < len(flat_items):
                item_entry = flat_items[idx]
                if item_entry[0] is not None:
                    item_id = item_entry[0]
                    if item_id in checked:
                        checked.discard(item_id)
                    else:
                        checked.add(item_id)
        except (ValueError, KeyboardInterrupt, EOFError):
            return cancel_returns
        print()

    return checked
