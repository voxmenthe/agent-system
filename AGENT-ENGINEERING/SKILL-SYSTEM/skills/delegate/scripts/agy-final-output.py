#!/usr/bin/env python3
"""Run AGY headlessly without exposing commentary, tools, or partial responses.

AGY's text output AND result.response concatenate all agent_response steps.
Reconstruct only the terminal completed step from stream-json text deltas.
Interactive invocations are exec'd unchanged. Explicit JSON output keeps the
result envelope, with response replaced; stream-json emits result events only.
"""

import json
import os
import subprocess
import sys


class OutputError(Exception):
    pass


VALUE_FLAGS = {
    "--add-dir", "--agent", "--conversation", "--effort", "--input-format",
    "--json-schema", "--log-file", "--mode", "--model", "--print-timeout",
    "--project", "--prompt-interactive", "-i",
}
PRINT_FLAGS = {"-p", "--print", "--prompt"}


def invocation(arguments):
    """Preserve values literally, including prompts that look like flags."""
    headless = False
    output_format = "text"
    forwarded = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            forwarded.extend(arguments[index:])
            break
        name, separator, value = argument.partition("=")
        # Go's flag parser also accepts single-dash long options (-print).
        if name.startswith("-") and not name.startswith("--") and len(name) > 2:
            name = "-" + name
        if name in PRINT_FLAGS or name == "--output-format" or name in VALUE_FLAGS:
            if not separator:
                if index + 1 >= len(arguments):
                    raise OutputError(f"{name} requires a value")
                index += 1
                value = arguments[index]
            if name == "--output-format":
                output_format = value
            else:
                forwarded.append(argument)
                if not separator:
                    forwarded.append(value)
            if name in PRINT_FLAGS or (name == "--input-format" and value == "stream-json"):
                headless = True
        else:
            forwarded.append(argument)
        index += 1
    if headless and output_format not in ("text", "json", "stream-json"):
        raise OutputError(f"unsupported output format: {output_format}")
    # Prefix so the option cannot land after the end-of-options delimiter.
    return headless, output_format, ["--output-format", "stream-json", *forwarded]


class FinalResponses:
    def __init__(self):
        self.steps = {}
        self.last_index = -1
        self.results = []
        self.pending = False

    def consume(self, event):
        if not isinstance(event, dict):
            raise OutputError("expected an AGY event object")
        kind = event.get("event")
        if kind == "step_update":
            step = event.get("step_update")
            if not isinstance(step, dict):
                raise OutputError("invalid step_update event")
            index = step.get("step_index")
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                raise OutputError("invalid step index")
            self.pending = True
            self.last_index = max(self.last_index, index)
            if step.get("step_type") == "agent_response":
                response = self.steps.setdefault(index, {"text": [], "state": None})
                delta = step.get("text_delta", "")
                if not isinstance(delta, str):
                    raise OutputError("invalid response delta")
                response["text"].append(delta)
                response["state"] = step.get("state")
        elif kind == "result":
            result = event.get("result")
            if not isinstance(result, dict):
                raise OutputError("invalid result event")
            if result.get("status") != "SUCCESS":
                # Do not include response: it can contain a full transcript.
                detail = result.get("error") or result.get("message") or result.get("status")
                raise OutputError(f"AGY did not succeed: {detail}")
            result = dict(result)
            if self.last_index >= 0:
                response = self.steps.get(self.last_index)
                if response is None or response["state"] != "DONE":
                    raise OutputError("no terminal completed agent response")
                final_text = "".join(response["text"])
                if not final_text.strip():
                    raise OutputError("terminal agent response is empty")
                result["response"] = final_text
            elif isinstance(result.get("command"), dict):
                # Slash commands have a CLI result, without agent/tool steps.
                final_text = result.get("response", "")
                if not isinstance(final_text, str):
                    raise OutputError("invalid command response")
            else:
                raise OutputError("result has no agent response steps")
            self.results.append(result)
            self.steps.clear()
            self.last_index = -1
            self.pending = False
        elif kind == "error":
            raise OutputError(f"AGY error: {event.get('error') or event.get('message') or 'unspecified'}")
        elif kind not in ("init", "command_result"):
            raise OutputError("unrecognized AGY event; refusing unfiltered output")

    def render(self, output_format):
        if not self.results or self.pending:
            raise OutputError("AGY ended without a complete final result")
        if output_format == "json" and len(self.results) != 1:
            raise OutputError("multiple results require text or stream-json output")
        rendered = []
        for result in self.results:
            if output_format == "text":
                value = result.get("response", "")
                if not value and "command" in result:
                    value = json.dumps(result["command"], ensure_ascii=False)
                rendered.append(value if value.endswith("\n") else value + "\n")
            elif output_format == "json":
                rendered.append(json.dumps(result, ensure_ascii=False) + "\n")
            else:
                rendered.append(json.dumps({"event": "result", "result": result}, ensure_ascii=False) + "\n")
        return "".join(rendered)


def main():
    if len(sys.argv) < 2:
        raise OutputError("AGY executable is required")
    executable, arguments = sys.argv[1], sys.argv[2:]
    headless, output_format, forwarded = invocation(arguments)
    if not headless:
        os.execv(executable, [executable, *arguments])
    # Child inherits stdin (including stream-json input) and stderr. Buffer all
    # final responses until a zero exit status; never replay raw stdout on error.
    child = subprocess.Popen([executable, *forwarded], stdout=subprocess.PIPE,
                             text=True, encoding="utf-8")
    responses = FinalResponses()
    parse_error = None
    try:
        for line in child.stdout:
            if parse_error is not None:
                continue  # Drain output so the child cannot block on its pipe.
            try:
                responses.consume(json.loads(line))
            except (ValueError, OutputError) as error:
                # JSON decode exceptions can quote input; keep malformed data out.
                parse_error = str(error) if isinstance(error, OutputError) else "malformed AGY event stream"
    except UnicodeError:
        parse_error = "invalid UTF-8 in AGY event stream"
        child.kill()
    except KeyboardInterrupt:
        child.terminate()
        child.wait()
        return 130
    finally:
        child.stdout.close()
    status = child.wait()
    if status:
        print(f"agy final output: process exited with status {status}", file=sys.stderr)
        if parse_error:
            print(f"agy final output: {parse_error}", file=sys.stderr)
        return status if status > 0 else 128 - status
    if parse_error:
        raise OutputError(parse_error)
    sys.stdout.write(responses.render(output_format))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OutputError, OSError) as error:
        print(f"agy final output: {error}", file=sys.stderr)
        sys.exit(1)
