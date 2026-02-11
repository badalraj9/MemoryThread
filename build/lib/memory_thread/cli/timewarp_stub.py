import typer

app = typer.Typer()

@app.command()
def insert(
    file: str = typer.Option(..., "--file"),
    output: str = typer.Option(None, "--output")
):
    typer.echo(f"Timewarp insert from {file}...")
    if output:
        import json
        with open(output, 'w') as f:
            json.dump({"status": "success"}, f)
