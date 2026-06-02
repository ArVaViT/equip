/**
 * Component-level a11y coverage for the overlay primitives.
 *
 * The page-level Playwright a11y spec catches the static surface; this
 * test pins the harder-to-cover overlay components which (a) render
 * via portal and (b) frequently regress when devs forget the
 * Title / aria-label triple. Each test renders the component in its
 * OPEN state via ``defaultOpen`` so the portaled content lands in the
 * DOM for axe to scan.
 *
 * NOTE: Only components actually exported from the project's ui
 * wrappers are tested — Dialog exports a narrow public surface, and
 * AlertDialog primitives are private (consumed via useConfirm /
 * ConfirmProvider). The component tests for those higher-level
 * patterns live alongside their feature consumers.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { axe } from "@/test/a11y";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";

describe("a11y — overlay primitives", () => {
  it("Dialog with header + title has no violations", async () => {
    const { baseElement } = render(
      <Dialog defaultOpen>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete course</DialogTitle>
          </DialogHeader>
          <p>
            This action cannot be undone. The course and its enrollments will
            be permanently removed.
          </p>
        </DialogContent>
      </Dialog>,
    );
    expect(await axe(baseElement)).toHaveNoViolations();
  });

  it("Sheet with title + description has no violations", async () => {
    const { baseElement } = render(
      <Sheet defaultOpen>
        <SheetContent side="right">
          <SheetHeader>
            <SheetTitle>Filters</SheetTitle>
            <SheetDescription>
              Adjust how courses are listed.
            </SheetDescription>
          </SheetHeader>
        </SheetContent>
      </Sheet>,
    );
    expect(await axe(baseElement)).toHaveNoViolations();
  });

  it("Popover with aria-label has no violations", async () => {
    // Radix renders PopoverContent as role="dialog"; axe's
    // ``aria-dialog-name`` rule requires an accessible name. Real
    // call sites either pass aria-label or wrap a heading. Pin the
    // aria-label path here so a future refactor that drops the
    // attribute surfaces a violation.
    const { baseElement } = render(
      <Popover defaultOpen>
        <PopoverTrigger asChild>
          <Button>Open</Button>
        </PopoverTrigger>
        <PopoverContent aria-label="Quick options">
          <p>Quick options panel.</p>
        </PopoverContent>
      </Popover>,
    );
    expect(await axe(baseElement)).toHaveNoViolations();
  });

  it("Tooltip with aria-labeled icon trigger has no violations", async () => {
    const { baseElement } = render(
      <TooltipProvider>
        <Tooltip defaultOpen>
          <TooltipTrigger asChild>
            <Button aria-label="Settings">
              <svg aria-hidden="true" focusable="false" width="14" height="14" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Settings</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    expect(await axe(baseElement)).toHaveNoViolations();
  });
});
