#!/bin/bash
#
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Trains and evaluates the neurosymbolic MNIST recognizer: the
# perceptron of examples/mnist plus hole features computed by Datalog
# recursion. Shares the /tmp/logica_mnist dataset with examples/mnist.
#
# If examples/mnist/run_mnist.sh ran before, the report additionally
# shows the digits that topology fixed: images the plain perceptron
# misread and this one reads correctly.

set -e

REPOSITORY="$(cd "$(dirname "$0")/../.." && pwd)"
DATA_DIRECTORY=/tmp/logica_mnist
MIRROR=https://ossci-datasets.s3.amazonaws.com/mnist

mkdir -p "$DATA_DIRECTORY"
for name in train-images-idx3-ubyte train-labels-idx1-ubyte \
            t10k-images-idx3-ubyte t10k-labels-idx1-ubyte; do
  if [ ! -f "$DATA_DIRECTORY/$name.gz" ]; then
    echo "Downloading $name.gz ..."
    curl -sSL -o "$DATA_DIRECTORY/$name.gz" "$MIRROR/$name.gz"
  fi
done

if [ ! -f "$DATA_DIRECTORY/mnist.duckdb" ]; then
  echo "Packing the dataset into DuckDB ..."
  python3 "$REPOSITORY/examples/mnist/prepare_mnist.py"
fi

echo "Counting holes, training and evaluating ..."
cd "$REPOSITORY"
export LOGICA_NEURAL_TRACE=1
time python3 logica.py examples/mnist_topology/mnist_topology.l \
  run_in_terminal Summary,PerDigit

echo "Rendering the report ..."
python3 examples/mnist/render_report.py \
  prediction_topology report_topology.html prediction
