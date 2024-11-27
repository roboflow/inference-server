import json
from typing import List, Tuple

import typer
from typer.testing import CliRunner
from typing_extensions import Annotated

from inference_cli.workflows import prepare_workflow_parameters

test_app = typer.Typer(help="This is test app to verify kwargs parsing")


@test_app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def verify_workflow_parameters_parsing(
    context: typer.Context,
    string_param: Annotated[
        str,
        typer.Option(
            "--string_param",
            "-sp",
        ),
    ],
    int_param: Annotated[
        int,
        typer.Option(
            "--int_param",
            "-ip",
        ),
    ],
    float_param: Annotated[
        float,
        typer.Option(
            "--float_param",
            "-fp",
        ),
    ],
    tuple_param: Annotated[
        Tuple[int, float, str],
        typer.Option(
            "--tuple_param",
            "-tp",
        ),
    ],
    list_param: Annotated[
        List[int],
        typer.Option(
            "--list_param",
            "-lp",
        ),
    ],
    bool_param: Annotated[
        bool,
        typer.Option("--yes/--no"),
    ],
    default_param: Annotated[
        str,
        typer.Option(
            "--default_param",
            "-dp",
        ),
    ] = "default",
) -> None:
    workflow_parameters = prepare_workflow_parameters(
        context=context,
        workflows_parameters_path=None,
    )
    print(
        json.dumps(
            {
                "string_param": string_param,
                "int_param": int_param,
                "float_param": float_param,
                "tuple_param": tuple_param,
                "list_param": list_param,
                "bool_param": bool_param,
                "default_param": default_param,
                "workflow_parameters": workflow_parameters,
            }
        )
    )


def test_command_parsing_workflows_parameters_when_no_additional_params_passed_and_long_param_names_used() -> (
    None
):
    # given
    runner = CliRunner()

    # when
    result = runner.invoke(
        test_app,
        "verify_workflow_parameters_parsing "
        "--string_param value "
        "--int_param 2137 "
        "--float_param 21.37 "
        "--tuple_param 2 1.0 37 "
        "--list_param 2 1 3 7 "
        "--yes".split(" "),
    )

    # then
    last_output_line = result.stdout.strip().split("\n")[-1]
    parsed_output = json.loads(last_output_line)
    assert parsed_output == {
        "string_param": "value",
        "int_param": 2137,
        "float_param": 21.37,
        "tuple_param": [2, 1.0, "37"],
        "list_param": [2],
        "bool_param": True,
        "default_param": "default",
        "workflow_parameters": None,
    }


def test_command_parsing_workflows_parameters_when_additional_params_passed_and_long_param_names_used() -> (
    None
):
    # given
    runner = CliRunner()

    # when
    result = runner.invoke(
        test_app,
        "verify_workflow_parameters_parsing "
        "--string_param value "
        "--int_param 2137 "
        "--float_param 21.37 "
        "--tuple_param 2 1.0 37 "
        "--list_param 2 1 3 7 "
        "--yes "
        "--additional_bool yes "
        "--additional_float 3.2 "
        "--additional_int 3 "
        "--additional_string custom "
        "--additional_list 1 2.0 some".split(" "),
    )

    # then
    last_output_line = result.stdout.strip().split("\n")[-1]
    parsed_output = json.loads(last_output_line)
    assert parsed_output == {
        "string_param": "value",
        "int_param": 2137,
        "float_param": 21.37,
        "tuple_param": [2, 1.0, "37"],
        "list_param": [2],
        "bool_param": True,
        "default_param": "default",
        "workflow_parameters": {
            "additional_bool": True,
            "additional_float": 3.2,
            "additional_int": 3,
            "additional_string": "custom",
            "additional_list": [1, 2.0, "some"],
        },
    }


def test_command_parsing_workflows_parameters_when_no_additional_params_passed_and_short_param_names_used() -> (
    None
):
    # given
    runner = CliRunner()

    # when
    result = runner.invoke(
        test_app,
        "verify_workflow_parameters_parsing "
        "-sp value "
        "-ip 2137 "
        "-fp 21.37 "
        "-tp 2 1.0 37 "
        "-lp 2 1 3 7 "
        "--yes "
        "-dp some".split(" "),
    )

    # then
    last_output_line = result.stdout.strip().split("\n")[-1]
    parsed_output = json.loads(last_output_line)
    assert parsed_output == {
        "string_param": "value",
        "int_param": 2137,
        "float_param": 21.37,
        "tuple_param": [2, 1.0, "37"],
        "list_param": [2],
        "bool_param": True,
        "default_param": "some",
        "workflow_parameters": None,
    }


def test_command_parsing_workflows_parameters_when_additional_params_passed_and_short_param_names_used() -> (
    None
):
    # given
    runner = CliRunner()

    # when
    result = runner.invoke(
        test_app,
        "verify_workflow_parameters_parsing "
        "-sp value "
        "-ip 2137 "
        "-fp 21.37 "
        "-tp 2 1.0 37 "
        "-lp 2 1 3 7 "
        "--yes "
        "--additional_bool yes "
        "--additional_float 3.2 "
        "--additional_int 3 "
        "--additional_string custom "
        "--additional_list 1 2.0 some".split(" "),
    )

    # then
    last_output_line = result.stdout.strip().split("\n")[-1]
    parsed_output = json.loads(last_output_line)
    assert parsed_output == {
        "string_param": "value",
        "int_param": 2137,
        "float_param": 21.37,
        "tuple_param": [2, 1.0, "37"],
        "list_param": [2],
        "bool_param": True,
        "default_param": "default",
        "workflow_parameters": {
            "additional_bool": True,
            "additional_float": 3.2,
            "additional_int": 3,
            "additional_string": "custom",
            "additional_list": [1, 2.0, "some"],
        },
    }


def test_command_parsing_workflows_parameters_when_no_additional_params_passed_and_short_mixed_names_used() -> (
    None
):
    # given
    runner = CliRunner()

    # when
    result = runner.invoke(
        test_app,
        "verify_workflow_parameters_parsing "
        "--string_param value "
        "-ip 2137 "
        "-fp 21.37 "
        "--tuple_param 2 1.0 37 "
        "-lp 2 1 3 7 "
        "--no "
        "-dp some".split(" "),
    )

    # then
    last_output_line = result.stdout.strip().split("\n")[-1]
    parsed_output = json.loads(last_output_line)
    assert parsed_output == {
        "string_param": "value",
        "int_param": 2137,
        "float_param": 21.37,
        "tuple_param": [2, 1.0, "37"],
        "list_param": [2],
        "bool_param": False,
        "default_param": "some",
        "workflow_parameters": None,
    }


def test_command_parsing_workflows_parameters_when_additional_params_passed_and_short_mixed_names_used() -> (
    None
):
    # given
    runner = CliRunner()

    # when
    result = runner.invoke(
        test_app,
        "verify_workflow_parameters_parsing "
        "--string_param value "
        "-ip 2137 "
        "-fp 21.37 "
        "--tuple_param 2 1.0 37 "
        "-lp 2 1 3 7 "
        "--no "
        "--additional_bool yes "
        "--additional_float 3.2 "
        "--additional_int 3 "
        "--additional_string custom "
        "--additional_list 1 2.0 some".split(" "),
    )

    # then
    last_output_line = result.stdout.strip().split("\n")[-1]
    parsed_output = json.loads(last_output_line)
    assert parsed_output == {
        "string_param": "value",
        "int_param": 2137,
        "float_param": 21.37,
        "tuple_param": [2, 1.0, "37"],
        "list_param": [2],
        "bool_param": False,
        "default_param": "default",
        "workflow_parameters": {
            "additional_bool": True,
            "additional_float": 3.2,
            "additional_int": 3,
            "additional_string": "custom",
            "additional_list": [1, 2.0, "some"],
        },
    }
