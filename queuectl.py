import click

@click.group()
def cli():
    pass

@cli.command()
def hello():
    click.echo("Hello, setup is complete!")

if __name__ == "__main__":
    cli()