#NOTE - need to SOURCE this file
# only works with ipython for some reason
. activate tensorflow_gpu
ipython /Users/simon.hughes/GitHub/tensorflow_models/tutorials/rnn/translate/translate.py -- --data_dir "/Users/simon.hughes/data/tensorflow/translate/cb/data_dir" --train_dir "/Users/simon.hughes/data/tensorflow/translate/cb/train_dir" --from_train_data "/Users/simon.hughes/data/tensorflow/translate/cb/Training/inputs.txt" --to_train_data "/Users/simon.hughes/data/tensorflow/translate/cb/Training/output_most_freq.txt" --from_dev_data "/Users/simon.hughes/data/tensorflow/translate/cb/Test/inputs.txt" --to_dev_data "/Users/simon.hughes/data/tensorflow/translate/cb/Test/output_most_freq.txt" --size=64 --batch_size=32 --from_vocab_size=4300 --to_vocab_size=14 --num_layers=1 --steps_per_checkpoint=10