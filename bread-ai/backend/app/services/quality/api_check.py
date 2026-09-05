"""Catching invented APIs in generated code, without running it.

The characteristic failure of a small coding model is not bad logic. It is
fluent, well-structured code that calls a function which does not exist. The
disnake example that motivated this module used ``discord.timedelta`` in a file
that never imported ``discord``, and passed ``intents`` to a ``run()`` that takes
no such argument. Both are deterministic, both are catchable, and neither needs
the code to be executed.

Three checks run here, in increasing order of how much they need to know:

``undefined``   a name is used that was never imported, assigned or built in
``attribute``   a module is imported, but the attribute taken from it is absent
``keyword``     a resolvable function is called with a keyword it does not accept

The first is pure syntax. The other two inspect the libraries actually installed
on this machine, which is why the report is specific to your environment: a
symbol added in a newer version shows as missing if you have the older one.

Importing libraries to inspect them is not the same as executing the generated
code. Nothing from the snippet is ever run. Even so, importing a third-party
package runs that package's module-level code, so it is gated behind
``allow_import`` and only ever touches modules already installed.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import importlib.util
import inspect
from dataclasses import dataclass, field
from typing import Any

BUILTIN_NAMES = set(dir(builtins))

# Names bound by the language itself rather than by an import or assignment.
IMPLICIT_NAMES = {"__name__", "__file__", "__doc__", "self", "cls", "_"}


@dataclass
class Finding:
    kind: str  # undefined | attribute | keyword | missing_module
    symbol: str
    line: int
    message: str
    # "certain" when the absence is provable, "likely" when the class could
    # still set the attribute at runtime. Reporting a suspicion as a fact is
    # the same failure the model makes, so the two are kept apart.
    confidence: str = "certain"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "symbol": self.symbol,
            "line": self.line,
            "message": self.message,
            "confidence": self.confidence,
        }


@dataclass
class ApiReport:
    findings: list[Finding] = field(default_factory=list)
    modules_checked: list[str] = field(default_factory=list)
    modules_unavailable: list[str] = field(default_factory=list)
    syntax_error: str | None = None

    @property
    def certain(self) -> list[Finding]:
        return [f for f in self.findings if f.confidence == "certain"]

    @property
    def likely(self) -> list[Finding]:
        return [f for f in self.findings if f.confidence != "certain"]

    @property
    def ok(self) -> bool:
        """True when nothing is provably wrong. Suspicions do not fail a check."""

        return not self.certain and self.syntax_error is None

    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "syntax_error": self.syntax_error,
            "findings": [finding.as_dict() for finding in self.findings],
            "by_kind": self.by_kind(),
            "modules_checked": self.modules_checked,
            "modules_unavailable": self.modules_unavailable,
        }


class _Scope(ast.NodeVisitor):
    """Collect every name the module binds, and every name it reads."""

    def __init__(self) -> None:
        self.bound: set[str] = set()
        self.imports: dict[str, str] = {}  # local alias -> dotted module path
        self.from_imports: list[tuple[str, str, int]] = []  # module, name, line
        self.reads: list[tuple[str, int]] = []
        self.attributes: list[tuple[str, str, int]] = []  # base alias, attr, line
        self.calls: list[tuple[str, str, list[str], int]] = []  # base, func, kwargs, line
        # Names whose type is knowable: `bot = commands.Bot(...)` and
        # `def f(member: disnake.Member)`. Maps local name -> (module alias, attr).
        # Scoping is not tracked, so a name annotated as two different types in
        # two functions is ambiguous and gets dropped rather than guessed at.
        self.typed_names: dict[str, tuple[str, str]] = {}
        self._ambiguous_names: set[str] = set()
        # Method calls on those names: name, method, kwargs, positional count, line
        self.method_calls: list[tuple[str, str, list[str], int, int]] = []
        # Plain attribute reads on typed names: name, attribute, line
        self.instance_attributes: list[tuple[str, str, int]] = []
        # local name -> (what to call it in a message, line). Used to report an
        # import nothing goes on to use.
        self.import_bindings: dict[str, tuple[str, int]] = {}
        self.declares_all = False

    # ------------------------------------------------------------- bindings
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.bound.add(local)
            self.imports[local] = alias.name if alias.asname else alias.name.split(".")[0]
            self.import_bindings[local] = (alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            self.bound.add(local)
            # A relative import (`from .sibling import thing`) has no meaning
            # outside its package, so it is recorded as bound and not checked.
            if alias.name != "*":
                label = f"{module}.{alias.name}" if module else alias.name
                self.import_bindings[local] = (label, node.lineno)
            if module and alias.name != "*" and not node.level:
                self.from_imports.append((module, alias.name, node.lineno))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._bind_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._bind_function(node)

    def _bind_function(self, node: Any) -> None:
        self.bound.add(node.name)
        self._bind_arguments(node.args)
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # `sorted(pairs, key=lambda pair: pair[1])` binds `pair` just as a def
        # would. Missing this made every lambda parameter look undefined.
        self._bind_arguments(node.args)
        self.generic_visit(node)

    def _bind_arguments(self, arguments: ast.arguments) -> None:
        for group in (
            arguments.posonlyargs,
            arguments.args,
            arguments.kwonlyargs,
        ):
            for argument in group:
                self.bound.add(argument.arg)
                annotation = argument.annotation
                if isinstance(annotation, ast.Attribute) and isinstance(annotation.value, ast.Name):
                    self._record_type(argument.arg, (annotation.value.id, annotation.attr))
        if arguments.vararg:
            self.bound.add(arguments.vararg.arg)
        if arguments.kwarg:
            self.bound.add(arguments.kwarg.arg)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bound.add(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            self.declares_all = True
        # `bot = commands.Bot(...)` tells us what `bot` is.
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
        ):
            self._record_type(
                node.targets[0].id,
                (node.value.func.value.id, node.value.func.attr),
            )
        self.generic_visit(node)

    def _record_type(self, name: str, resolved: tuple[str, str]) -> None:
        existing = self.typed_names.get(name)
        if existing is not None and existing != resolved:
            self._ambiguous_names.add(name)
            self.typed_names.pop(name, None)
            return
        if name not in self._ambiguous_names:
            self.typed_names[name] = resolved

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound.add(node.id)
        else:
            self.reads.append((node.id, node.lineno))
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        # `case Timeout() as error:` and `case [first, second]:` bind names that
        # never appear as Name nodes.
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.bound.add(node.rest)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self.bound.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.bound.update(node.names)

    # ---------------------------------------------------------------- usage
    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name):
            self.attributes.append((node.value.id, node.attr, node.lineno))
            self.instance_attributes.append((node.value.id, node.attr, node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        keywords = [kw.arg for kw in node.keywords if kw.arg]
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            self.calls.append((node.func.value.id, node.func.attr, keywords, node.lineno))
            self.method_calls.append(
                (
                    node.func.value.id,
                    node.func.attr,
                    keywords,
                    len(node.args),
                    node.lineno,
                )
            )
        elif isinstance(node.func, ast.Name):
            self.calls.append(("", node.func.id, keywords, node.lineno))
        self.generic_visit(node)


def _import_module(name: str) -> Any | None:
    try:
        if importlib.util.find_spec(name) is None:
            return None
    except (ImportError, ValueError, ModuleNotFoundError):
        return None
    try:
        return importlib.import_module(name)
    except Exception:
        # A library that cannot be imported here cannot be checked here. That is
        # a gap in the report, not a finding about the generated code.
        return None


def check_code(
    code: str,
    *,
    allow_import: bool = False,
    extra_names: set[str] | None = None,
) -> ApiReport:
    """Inspect generated Python for references that cannot resolve."""

    report = ApiReport()
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        report.syntax_error = f"line {error.lineno}: {error.msg}"
        return report

    scope = _Scope()
    scope.visit(tree)

    # Library wiring the generic checks cannot see: an intent that is not
    # enabled, a cog nothing loads, a blocking call inside async code.
    from .frameworks import check_frameworks

    report.findings.extend(check_frameworks(tree))

    known = scope.bound | BUILTIN_NAMES | IMPLICIT_NAMES | (extra_names or set())

    # ------------------------------------------------------- undefined names
    seen: set[str] = set()
    for name, line in scope.reads:
        if name in known or name in seen:
            continue
        seen.add(name)
        report.findings.append(
            Finding(
                kind="undefined",
                symbol=name,
                line=line,
                message=f"`{name}` is used but never imported, assigned or defined",
            )
        )

    # ----------------------------------------------------------- dead imports
    # An import nothing uses is usually a leftover from code that was adapted
    # rather than written, and the leftover is a hint that more was carried over
    # than the author meant to carry.
    if not scope.declares_all:
        # A module with `__all__` is a re-export surface, where an unused import
        # is the point.
        used = {name for name, _line in scope.reads}
        used |= {alias for alias, _attr, _line in scope.attributes}
        for local, (label, line) in sorted(
            scope.import_bindings.items(), key=lambda item: item[1][1]
        ):
            if local in used or local.startswith("_"):
                continue
            if label.startswith("__future__."):
                # A future import changes how the file is compiled. It is never
                # "used" by name and removing it changes behaviour.
                continue
            report.findings.append(
                Finding(
                    kind="unused_import",
                    symbol=label,
                    line=line,
                    confidence="likely",
                    message=f"`{label}` is imported but never used",
                )
            )

    if not allow_import:
        return report

    # ------------------------------------------------- module-aware checking
    modules: dict[str, Any] = {}
    for alias, dotted in scope.imports.items():
        module = _import_module(dotted)
        if module is None:
            report.modules_unavailable.append(dotted)
            continue
        modules[alias] = module
        report.modules_checked.append(dotted)

    for module_name, symbol, line in scope.from_imports:
        module = _import_module(module_name)
        if module is None:
            if module_name not in report.modules_unavailable:
                report.modules_unavailable.append(module_name)
            continue
        if module_name not in report.modules_checked:
            report.modules_checked.append(module_name)
        if not hasattr(module, symbol) and _import_module(f"{module_name}.{symbol}") is None:
            report.findings.append(
                Finding(
                    kind="attribute",
                    symbol=f"{module_name}.{symbol}",
                    line=line,
                    message=f"`{module_name}` has no `{symbol}` in the installed version",
                )
            )

    reported: set[str] = set()
    for alias, attribute, line in scope.attributes:
        module = modules.get(alias)
        if module is None:
            continue
        key = f"{alias}.{attribute}"
        if key in reported or hasattr(module, attribute):
            continue
        reported.add(key)
        report.findings.append(
            Finding(
                kind="attribute",
                symbol=key,
                line=line,
                message=f"`{alias}` has no attribute `{attribute}` in the installed version",
            )
        )

    # ---------------------------------------------------- keyword arguments
    for alias, function_name, keywords, line in scope.calls:
        if not keywords or not alias:
            continue
        module = modules.get(alias)
        if module is None:
            continue
        target = getattr(module, function_name, None)
        if target is None or not callable(target):
            continue
        try:
            signature = inspect.signature(target)
        except (TypeError, ValueError):
            continue
        if any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        ):
            continue
        for keyword in keywords:
            if keyword not in signature.parameters:
                report.findings.append(
                    Finding(
                        kind="keyword",
                        symbol=f"{alias}.{function_name}({keyword}=...)",
                        line=line,
                        message=f"`{alias}.{function_name}()` takes no `{keyword}` argument",
                    )
                )

    # ------------------------------------------- calls on resolved instances
    _check_instance_calls(scope, modules, report)

    return report


def _resolve_class(scope: _Scope, modules: dict[str, Any], name: str) -> tuple[str, Any] | None:
    """Resolve a local name to the class it was annotated or assigned as."""

    typed = scope.typed_names.get(name)
    if typed is None:
        return None
    module_alias, attribute = typed
    module = modules.get(module_alias)
    if module is None:
        return None
    target = getattr(module, attribute, None)
    if not inspect.isclass(target):
        return None
    return f"{module_alias}.{attribute}", target


def _is_declared_field(klass: Any, attribute: str) -> bool:
    """True when a class declares the attribute without setting it on itself.

    AST nodes list their children in ``_fields``, and dataclasses, attrs classes
    and pydantic models declare theirs in ``__annotations__``. In all of those
    the attribute exists on instances only, so ``hasattr`` on the class says
    nothing and reporting it would be noise.
    """

    for base in klass.__mro__:
        if attribute in getattr(base, "_fields", ()):
            return True
        if attribute in getattr(base, "__annotations__", {}):
            return True
    return False


def _check_instance_calls(scope: _Scope, modules: dict[str, Any], report: ApiReport) -> None:
    """Check method calls on names whose class is known.

    Only fires when the class is resolvable and does not define ``__getattr__``,
    because a class with dynamic attributes cannot be checked this way without
    producing false positives.
    """

    reported: set[str] = set()

    # Attribute reads on a name whose class we know.
    called = {(name, method) for name, method, _kw, _pos, _line in scope.method_calls}
    for name, attribute, line in scope.instance_attributes:
        if name in modules or (name, attribute) in called:
            continue
        resolved = _resolve_class(scope, modules, name)
        if resolved is None:
            continue
        class_path, klass = resolved
        if "__getattr__" in vars(klass) or hasattr(klass, attribute):
            continue
        if _is_declared_field(klass, attribute):
            continue

        key = f"{name}.{attribute}"
        if key in reported:
            continue
        reported.add(key)

        # A fully slotted class cannot gain attributes at runtime, so absence is
        # provable. Otherwise it is a strong suspicion and labelled as one.
        fully_slotted = all(
            "__slots__" in vars(base) for base in klass.__mro__ if base is not object
        )
        report.findings.append(
            Finding(
                kind="attribute",
                symbol=key,
                line=line,
                message=f"`{class_path}` has no attribute `{attribute}`"
                + ("" if fully_slotted else "; it may be set at runtime"),
                confidence="certain" if fully_slotted else "likely",
            )
        )

    for name, method, keywords, positional, line in scope.method_calls:
        if name in modules:
            continue  # module-level calls are handled above
        resolved = _resolve_class(scope, modules, name)
        if resolved is None:
            continue
        class_path, klass = resolved
        if "__getattr__" in vars(klass):
            continue

        function = getattr(klass, method, None)
        key = f"{name}.{method}"
        if function is None:
            if key not in reported:
                reported.add(key)
                report.findings.append(
                    Finding(
                        kind="attribute",
                        symbol=key,
                        line=line,
                        message=f"`{class_path}` has no method `{method}`",
                    )
                )
            continue

        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError):
            continue

        parameters = list(signature.parameters.values())
        accepts_var_positional = any(
            parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters
        )
        accepts_var_keyword = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters
        )

        if not accepts_var_keyword:
            for keyword in keywords:
                if keyword not in signature.parameters:
                    report.findings.append(
                        Finding(
                            kind="keyword",
                            symbol=f"{key}({keyword}=...)",
                            line=line,
                            message=f"`{class_path}.{method}()` takes no `{keyword}` argument",
                        )
                    )

        if accepts_var_positional:
            continue

        # `self` is bound by the call, so the callable's own count includes it.
        allowed_positional = sum(
            1
            for parameter in parameters
            if parameter.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        )
        allowed_positional = max(allowed_positional - 1, 0)
        if positional > allowed_positional:
            report.findings.append(
                Finding(
                    kind="keyword",
                    symbol=f"{key}()",
                    line=line,
                    message=f"`{class_path}.{method}()` takes {allowed_positional} "
                    f"positional argument(s), {positional} given; the rest are "
                    "keyword-only",
                )
            )


def check_answer(answer: str, *, allow_import: bool = False) -> ApiReport:
    """Pull the code out of a model's answer and check it."""

    from .coding_eval import extract_code
    from .packaging import check_install_instructions

    code = extract_code(answer)
    if not code.strip():
        report = ApiReport()
        report.syntax_error = "no code block in the answer"
        return report
    report = check_code(code, allow_import=allow_import)
    # Only an answer has install instructions to be inconsistent with, so this
    # check lives here rather than in `check_code`.
    report.findings.extend(check_install_instructions(answer, code))
    return report
