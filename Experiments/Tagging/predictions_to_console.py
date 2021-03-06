def predictions_to_console(ys_by_code, predictions_by_code, essays, codes):

    def sort_key(code):
        if code[0].isdigit():
            return (-1, len(code), code)
        return (1, len(code), code)

    ix = 0
    for essay_ix, essay in enumerate(essays):
        for sent_ix, tagged_sentence in enumerate(essay.sentences):
            predictions = set()
            actual = set()
            for code in codes:
                if code in ys_by_code:
                    y_val = ys_by_code[code][ix]
                    if y_val > 0:
                        actual.add(code)
                    # some codes are not yet predicted
                if code in predictions_by_code:
                    pred_y_val = predictions_by_code[code][ix]
                    if pred_y_val > 0:
                        predictions.add(code)

            words = map(lambda ft: ft.word, tagged_sentence)
            s_words = " ".join(words)
            print("|".join([essay.name, str(sent_ix + 1), s_words, ",".join(sorted(actual, key=sort_key)), ",".join(sorted(predictions, key=sort_key))]))
            ix += 1
    pass
