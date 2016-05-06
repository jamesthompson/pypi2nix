import os
import click
import random
import string
import pypi2nix.wheelhouse
import pypi2nix.parse_wheels
import pypi2nix.stage3


PYTHON_VERSIONS = {
    "2.6": "python26",
    "2.7": "python27",
    "3.2": "python32",
    "3.3": "python33",
    "3.4": "python34",
    "3.5": "python35",
    "pypy": "pypy",
}


@click.command()
@click.option(
    '-I', '--nix-path',
    envvar='NIX_PATH',
    multiple=True,
    default=None,
    help=u'Add a path to the Nix expression search path. This option may be '
         u'given multiple times. See the NIX_PATH environment variable for '
         u'information on the semantics of the Nix search path. Paths added '
         u'through -I take precedence over NIX_PATH.',
)
@click.option(
    '-E', '--extra-build-inputs',
    default=None,
    help=u'Extra build dependencies needed for installation of required '
         u'python packages.'
)
@click.option(
    '-V', '--python-version',
    required=True,
    default="2.7",
    type=click.Choice(PYTHON_VERSIONS.keys()),
    help=u'Provide which python version we build for.',
)
@click.option(
    '-r', '--requirements',
    required=False,
    default=None,
    type=click.Path(exists=True),
    help=u'',
)
@click.option(
    '-b', '--buildout',
    required=False,
    default=None,
    type=click.Path(exists=True),
    help=u'TODO',
)
@click.option(
    '--name',
    required=False,
    default=None,
    help=u'TODO',
)
@click.argument(
    'specification',
    nargs=-1,
    required=False,
    default=None,
)
def main(specification, name, requirements, buildout, nix_path,
         extra_build_inputs, python_version):
    '''
        INPUT_FILE should be requirements.txt (output of pip freeze).
    '''

    home_dir = os.path.expanduser('~/.pypi2nix')
    if not os.path.isdir(home_dir):
        os.makedirs(home_dir)

    _input = [specification, requirements, buildout]

    if not any(_input):
        raise click.exceptions.UsageError(
            u'Please tell what you want to be packages by specifying `-b` '
            u'(buildout.cfg), `-r` (requirements.txt) or by providing '
            u'package specification as a argument of pypi2nix command')

    if len(filter(lambda x: x, _input)) >= 2:
        raise click.exceptions.UsageError(
            u'Please only specify one of the options: `-b`, `-r` or package.')

    if buildout:
        raise click.exceptions.ClickException(
            u'Not yet implemented!')

    elif requirements:
        input_file = requirements
        input_name = os.path.splitext(os.path.basename(input_file))[0]

    elif specification:
        input_name = '_'.join(specification)
        input_file = os.path.expanduser(os.path.join(
            '~/.pypi2nix', 'requirements-%s.txt' % (''.join(
                random.choice(string.ascii_uppercase + string.digits)
                for _ in range(6)))))
        with open(input_file, 'w+') as f:
            f.write('\n'.join(specification))

    if name:
        input_name = name

    #
    # Stage 1
    #
    # from setup.py or buildout.cfg we create complete list of all requirements
    # needed.
    #
    click.secho('Downloading wheels and creating wheelhouse', fg='green')
    wheels_dir = pypi2nix.wheelhouse.do(
        input_file, nix_path, extra_build_inputs,
        PYTHON_VERSIONS[python_version])

    #
    # Stage 2
    #
    # once we have all the metadata we can create wheels and install them, so
    # that metadata.json is produced for each package which we process to
    # extract dependencies for packages
    #
    click.secho(
        'Stage2: Extracting metadata from {}'.format(wheels_dir), fg='green')
    metadata = pypi2nix.parse_wheels.do(wheels_dir)
    click.secho(
        'Got metadata from {:d} packages'.format(len(metadata)), fg='green')

    #
    # Stage 3
    #
    # With all above we can now generate nix expressions
    #
    base_dir = os.getcwd()
    default_file = os.path.join(base_dir, '{}.nix'.format(input_name))
    generate_file = os.path.join(
        base_dir, '{}_generated.nix'.format(input_name))
    override_file = os.path.join(
        base_dir, '{}_override.nix'.format(input_name))

    with open(input_file) as f:
        pypi2nix.stage3.do(metadata, generate_file)

    if not os.path.exists(override_file):
        with open(override_file, 'wa+') as f:
            write = lambda x: f.write(x + '\n')
            write("{ pkgs, python }:")
            write("")
            write("self: super: {")
            write("}")

    if not os.path.exists(default_file):
        with open(default_file, 'wa+') as f:
            write = lambda x: f.write(x + '\n')
            write("{ system ? builtins.currentSystem")
            write(", nixpkgs ? <nixpkgs>")
            write("}:")
            write("")
            write("let")
            write("")
            write("  inherit (pkgs.stdenv.lib) fix' extends;")
            write("")
            write("  pkgs = import nixpkgs { inherit system; };")
            write("  pythonPackages = pkgs.%sPackages;" % (
                PYTHON_VERSIONS[python_version]))
            write("")
            write("  python = {")
            write("    interpreter = pythonPackages.python;")
            write("    mkDerivation = pythonPackages.buildPythonPackage;")
            write("    modules = pythonPackages.python.modules;")
            write("    overrideDerivation = drv: f: pythonPackages.buildPythonPackage (drv.drvAttrs // f drv.drvAttrs);")
            write("    pkgs = pythonPackages;")
            write("  };")
            write("")
            write("  generated = import %s { inherit pkgs python; };" % generate_file)
            write("  overrides = import %s { inherit pkgs python; };" % override_file)
            write("")
            write("in fix' (extends overrides generated)")
