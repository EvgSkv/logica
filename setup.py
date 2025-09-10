import setuptools
from setuptools.command.build_py import build_py as _build_py


class build_py(_build_py):
  def find_package_modules(self, package, package_dir):
    modules = super().find_package_modules(package, package_dir)
    filtered = []
    for pkg, mod, filename in modules:
      if (mod.endswith('_test') or mod.startswith('test') or 'tests' in filename):
        continue
      filtered.append((pkg, mod, filename))
    return filtered

with open("README.md", "r") as f:
  long_description = f.read()

setuptools.setup(
  name = "logica",
  version = "1.3.141592",
  author = "Evgeny Skvortsov",
  author_email = "logica@evgeny.ninja",
  description = "Logica language.",
  long_description = long_description,
  long_description_content_type = "text/markdown",
  url="https://github.com/evgskv/logica",
  packages=setuptools.find_namespace_packages(
    include=[
      "common*",
      "compiler*",
      "parser_py*",
      "tools*",
      "type_inference*",
    ],
    exclude=[
      "examples*",
      "integration_tests*",
      "type_inference/tests*",
      "type_inference/research/integration_tests*",
      "docs*",
      "tutorial*",
      "syntax*",
    ],
  ),
  py_modules=["logica"],
  include_package_data=True,
  classifiers = [
      "Topic :: Database",
      "License :: OSI Approved :: Apache Software License"
  ],
  entry_points = {
    'console_scripts': ['logica=logica:run_main']
  },
  python_requires= ">=3.0"
  ,
  cmdclass={
    'build_py': build_py
  }
)