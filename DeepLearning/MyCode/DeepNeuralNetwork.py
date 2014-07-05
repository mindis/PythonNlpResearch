'''
Created on Aug 18, 2013
@author: simon.hughes

Auto-encoder implementation. Can be used to implement a denoising auto-encoder, sparse or contractive auto-encoder
'''

import numpy as np
import gnumpy as gp
from numpy import random

USE_GPU = False


def get_array(a):
    if USE_GPU:
        if type(a) == gp.garray:
            return a
        return gp.garray(a)

    #ELSE NP
    if type(a) == np.array:
        return a
    return np.array(a)

def reverse_layers(layers):
    """ For flipping auto encoders and other deep networks,
        makes a copy of the layers but in reverse, sharing the weights and bias'

        layers = a list of Layer

        returns a list of Layer
    """
    rev_layers = []
    for i in range(len(layers)):
        layer = layers[i]
        bias = None if i == 0 else layers[i - 1].bias
        l = Layer(layer.num_outputs, layer.num_inputs, activation_fn=layer.activation_fn, weights=layer.weights.T,
                  bias=bias)
        rev_layers.insert(0, l)
    return rev_layers

class Layer(object):
    def __init__(self, num_inputs, num_outputs, activation_fn="tanh", momentum=0.5, weight_decay=0.0, weights=None, bias=None):
        self.activation_fn = activation_fn
        self.num_outputs = num_outputs
        self.num_inputs = num_inputs
        self.weight_decay = weight_decay
        self.momentum = momentum

        init_min, init_max = self.__initial_weights_min_max__()

        if weights is None:
            weights = np.random.uniform(low=init_min, high=init_max, size=(self.num_outputs, self.num_inputs))

        if bias is None:
            if self.activation_fn == "relu":
                # enforce positive
                bias = np.ones((num_outputs, 1))
            else:
                bias = np.zeros((num_outputs, 1))

        self.weights        = weights
        self.bias           = bias

        #Force creation of best weights\bias
        self.save_state()
        #Moving Average of weights update
        self.ma_weights = None

        assert self.num_inputs == self.weights.shape[1]
        assert self.num_outputs == self.weights.shape[0]
        assert self.num_outputs == self.bias.shape[0]

    def __initial_weights_min_max__(self):
        if self.activation_fn == "tanh":
            val = np.sqrt(6.0 / (self.num_inputs + self.num_inputs))
            return (-val, val)
        elif self.activation_fn == "sigmoid" or self.activation_fn == "softmax":
            val = np.sqrt(4 * (6.0 / (self.num_inputs + self.num_inputs)))
            return (-val, val)
        elif self.activation_fn == "linear" or self.activation_fn == "relu":
            #for relu we set the bias' to 1, ensuring activations on positive inputs
            return (-0.001, 0.001)

    def clone(self):
        return Layer( self.num_inputs, self.num_outputs, self.activation_fn, self.momentum, self.weight_decay, self.best_weights.copy(), self.best_bias.copy())

    def save_state(self):
        self.best_weights   = self.weights.copy()
        self.best_bias      = self.bias.copy()

    def revert_state(self):
        self.weights        = self.best_weights.copy()
        self.bias           = self.best_bias.copy()

    # for prediction (for case like dropout where we need to do something different
    # here by overriding this function
    def feed_forward(self, inputs_T):
        z = self.__compute_z__(inputs_T, self.best_weights, self.best_bias)
        a = self.__activate__(z, self.activation_fn)
        return (z, a)

    # for training
    def prop_up(self, inputs_T):

        """ Compute activations """
        z = self.__compute_z__(inputs_T, self.weights, self.bias)
        a = self.__activate__(z, self.activation_fn)
        return (z, a)

    def update(self, wtdiffs, biasdiff):

        if self.ma_weights is None:
            momentum_update = wtdiffs
        else:
            momentum_update = self.momentum * self.ma_weights + (1.0-self.momentum) * wtdiffs

        self.weights -= momentum_update
        self.bias    -= biasdiff

        self.ma_weights = momentum_update

    def derivative(self, activations):

        if self.activation_fn == "sigmoid":
            """ f(z)(1 - f(z)) """
            return np.multiply(activations, (1.0 - activations))

        elif self.activation_fn == "softmax":
            # So long as we correctly compute the soft max output, derivative is linear
            return np.ones(activations.shape)

        elif self.activation_fn == "tanh":
            """ 1 - f(z)^2 """
            return 1.0 - np.square(activations)

        elif self.activation_fn == "linear":
            return np.ones(activations.shape)

        elif self.activation_fn == "relu":
            copy = activations.copy() # don't modify vector
            copy[copy < 0] = 0
            copy[copy > 0] = 1.0
            return copy
        else:
            raise NotImplementedError("Only sigmoid, tanh, linear and relu currently implemented")

    def __compute_z__(self, inputs_T, weights, bias):
        #Can we speed this up by making the bias a column vector?
        return np.dot(weights, inputs_T) + bias

    def __activate__(self, zs, activation_fn):

        if activation_fn == "sigmoid":
            return 1 / (1 + np.exp(-zs))

        elif activation_fn == "softmax":
            exponents = np.exp(zs)
            totals = exponents.sum(axis=0)
            if len(totals.shape) == 1:
                totals = totals.reshape((1, len(totals)))
            return exponents / totals

        elif activation_fn == "tanh":
            return np.tanh(zs)
        elif activation_fn == "linear":
            return zs
        elif activation_fn == "relu":
            copy = zs.copy()
            copy[copy < 0] = 0
            return copy
        else:
            raise NotImplementedError("Only sigmoid, tanh, softmax, linear and relu currently implemented")

    def __repr__(self):
        return str(self.weights.shape[1]) + "->" + str(self.weights.shape[0]) + " : " + self.activation_fn

def dropout_mask(inputs_T, drop_out_prob):
    mask = np.matlib.rand(inputs_T.shape)
    mask[mask >= drop_out_prob] = 1.0
    mask[mask <  drop_out_prob] = 0.0
    return mask

class DropOutLayer(Layer):

    def __init__(self, num_inputs, num_outputs, activation_fn="tanh", drop_out_prob = 0.5, weight_decay=0.0, weights=None, bias=None):
        Layer.__init__(self, num_inputs, num_outputs, activation_fn, weight_decay, weights, bias)
        self.drop_out_prob = drop_out_prob

    def feed_forward(self, inputs_T):
        wts = self.best_weights * (1.0 - self.drop_out_prob)
        z = self.__compute_z__(inputs_T, wts, self.best_bias)
        a = self.__activate__(z, self.activation_fn)
        return (z, a)

    def clone(self):
        return DropOutLayer(self.num_inputs, self.num_outputs,
                            self.activation_fn, self.drop_out_prob,
                            self.best_weights.copy(), self.best_bias.copy())

    def revert_state(self):
        pass

class MLP(object):
    '''
    classdocs
    '''

    def __init__(self, layers, learning_rate=0.1, weight_decay=0.0, epochs = 50, batch_size = 32,
                 lr_increase_multiplier = 1.0, lr_decrease_multiplier = 1.0):
        '''
        learning_rate           = the learning rate
        weight_decay            = a regularization term to stop over-fitting. Only turn on if network converges too fast or overfits the data
        epochs                  = number of epochs to train for. Can be overridden when calling fit
        batch_size              = mini batch size. Can be overridden when calling fit
        lr_increase_multiplier  = factor used to multiply the learning rate by if error decreeases
        lr_decrease_multiplier  = factor used to multiply the learning rate by if error increases
        '''

        """ Properties """
        self.layers = layers
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr_increase_multiplier = lr_increase_multiplier
        self.lr_decrease_multiplier = lr_decrease_multiplier
        """ END Properties """
        self.lst_mse = []
        self.lst_mae = []

    def predict(self, inputs, layer_ix = np.inf, layers = None):
        if layers is None:
            layers = self.layers
        a = self.__ensure_vector_format__(inputs).T
        for i, layer in enumerate(layers):
            z, a = layer.feed_forward(a)
            if i == layer_ix:
                break
        return a.T

    def fit(self, xs, ys, min_error=0.000001, epochs = None, batch_size = None):

        if epochs is None:
            epochs = self.epochs
        if batch_size is None:
            batch_size = self.batch_size

        inputs  = self.__ensure_vector_format__(xs)
        outputs = self.__ensure_vector_format__(ys)

        num_rows = inputs.shape[0]

        """ Number of rows in inputs should match those in outputs """
        assert inputs.shape[0] == outputs.shape[0], "Xs and Ys do not have the same row count"

        assert inputs.shape[1]  == self.layers[0].weights.shape[1],  "The input layer does not match the Xs column count"
        assert outputs.shape[1] == self.layers[-1].weights.shape[0], "The output layer does not match the Ys column count"

        """ Check outputs match the range for the activation function for the layer """
        self.__validate_outputs__(outputs, self.layers[-1])

        num_batches = num_rows / batch_size
        if num_rows % batch_size > 0:
            num_batches += 1

        mse = -1.0
        mae = -1.0

        ixs = range(len(xs))
        for epoch in range(epochs):

            """ Shuffle the dataset on each epoch """
            np.random.shuffle(ixs)
            inputs = inputs[ixs]
            outputs = outputs[ixs]
            """ Note that the error may start increasing exponentially at some point
                if so, halt training
            """

            errors = []
            for batch in range(num_batches):
                start = batch * batch_size
                end = start + batch_size
                mini_batch_in = inputs[start:end]
                mini_batch_out = outputs[start:end]
                if len(mini_batch_in) == 0:
                    continue

                mini_batch_errors, gradients = self.__compute_gradient__(mini_batch_in, mini_batch_out, len(xs),
                                                                         self.layers, self.learning_rate)
                if np.any(np.isnan(mini_batch_errors)):
                    print "Nans in errors. Stopping"
                    self.__reset_layers__()
                    return (mse, mae)

                errors.extend(mini_batch_errors)

                # apply weight updates
                for layer, gradient in zip(self.layers, gradients):
                    wds, bds = gradient
                    layer.update(wds, bds)

            errors = get_array(errors)
            mse = np.mean(np.square(errors))
            mae = np.mean(np.abs(errors))

            DIGITS = 8
            print "MSE for epoch {0} is {1}".format(epoch, np.round(mse,DIGITS)),
            print "\tMAE for epoch {0} is {1}".format(epoch, np.round(mae,DIGITS)),
            print "\tlearning rate is {0}".format(self.learning_rate)
            if len(self.lst_mae) > 0:
                self.__adjust_learning_rate__(self.lst_mae[-1], mae)
            if mse <= min_error:
                print "MSE is %s. Stopping" % str(mse)
                return (mse, mae)
            self.lst_mse.append(mse)
            self.lst_mae.append(mae)
        return (mse, mae)

    """ Gradient Checking """
    def estimate_gradient(self, xs, ys, layers = None, epsilon = 0.0001, input_masks = None):

        if layers is None:
            layers = self.layers[::]

        loss_type = "mse"
        if layers[-1].activation_fn == "softmax":
            loss_type = "crossentropy"

        layer_gradient = []
        for ix,l in enumerate(layers):
            wgrad = np.zeros(l.best_weights.shape)
            bgrad = np.zeros(l.best_bias.shape)

            layer_gradient.append((wgrad, bgrad))

            for i in range(l.best_weights.shape[0]):
                for j in range(l.best_weights.shape[1]):

                    p_clone = l.clone()
                    n_clone = l.clone()

                    p_layers = layers[::]
                    p_layers[ix] = p_clone

                    n_layers = layers[::]
                    n_layers[ix] = n_clone

                    p_clone.best_weights[i,j] += epsilon
                    n_clone.best_weights[i,j] -= epsilon


                    p_loss = self.loss(xs, ys, p_layers, loss_type=loss_type, input_masks=input_masks )
                    n_loss = self.loss(xs, ys, n_layers, loss_type=loss_type, input_masks=input_masks)
                    wgrad[i,j] = ((p_loss - n_loss) / (2*epsilon)).sum()

            for i in range(len(l.best_bias)):
                p_clone = l.clone()
                n_clone = l.clone()

                p_layers = layers[::]
                p_layers[ix] = p_clone

                n_layers = layers[::]
                n_layers[ix] = n_clone

                p_clone.best_bias[i] += epsilon
                n_clone.best_bias[i] -= epsilon

                p_loss = self.loss(xs, ys, p_layers, loss_type=loss_type, input_masks=input_masks)
                n_loss = self.loss(xs, ys, n_layers, loss_type=loss_type, input_masks=input_masks)
                bgrad[i] = ((p_loss - n_loss) / (2 * epsilon)).sum()

        return layer_gradient

    def loss(self, input_vectors, outputs, layers = None, loss_type="mse", input_masks = None):

        # Note that this function does not transpose the inputs or outputs
        # Each row is a separate example \ label (i.e. row not column vectors)
        if layers is None:
            layers = self.layers

        # Predict
        a = self.__ensure_vector_format__(input_vectors).T
        for i, layer in enumerate(layers):
            if input_masks is not None \
                and input_masks[i] is not None:
                a = np.multiply(a, input_masks[i])

            # Ensure method called on layer not drop out layer
            z, a = Layer.feed_forward(layer, a)
        predictions = a.T

        # error loss
        if loss_type == "mse":
            errors = predictions - outputs
            error_loss = (0.5 * ( np.multiply(errors, errors))  ).mean(axis=0)
        elif loss_type == "crossentropy":
            error_loss = -((np.multiply(  outputs , np.log(predictions)).sum(axis=1).mean()))
        else:
            raise Exception("Unknown loss type: " + loss_type)

        # weight decay loss
        weight_decay_loss = 0.0
        for l in layers:
            if l.weight_decay > 0.0:
                weight_decay_loss += (l.weight_decay / 2.0) * (l.best_weights ** 2.0).sum()

        # return combined loss function
        return error_loss + weight_decay_loss

    def verify_gradient(self, xs, ys):

        epsilon = 0.00001
        input_masks = []
        rows = xs.shape[0]

        momentums = [l.momentum for l in self.layers]

        for l in self.layers:
            l.momentum = 0.0
            if type(l) == DropOutLayer:
                input_masks.append( dropout_mask(np.ones((l.weights.shape[1],rows)), l.drop_out_prob) )
            else:
                input_masks.append(None)

        errors, grad = self.__compute_gradient__(xs, ys, len(xs), self.layers, 1.0, input_masks)
        grad_est = self.estimate_gradient(xs, ys, self.layers, epsilon, input_masks)

        for i in range(len(grad)):
            wdelta, bdelta = grad[i]
            est_wdelta, est_bdelta = grad_est[i]

            max_wts_diff  = np.max(np.abs( wdelta - est_wdelta ))
            max_bias_diff = np.max(np.abs( bdelta - est_bdelta ))
            if max_wts_diff  > epsilon:
                print "Estimated"
                print est_wdelta
                print "Actual"
                print wdelta
                assert 1==2, "Significant Difference in estimated versus computed weights gradient: " + str(max_wts_diff)

            if max_bias_diff > epsilon:
                print "Estimated"
                print est_bdelta
                print "Actual"
                print bdelta
                assert 1==2, "Significant Difference in estimated versus computed bias gradient :" + str(max_bias_diff)

            print i, "Max Wt Diff:", str(max_wts_diff), "Max Bias Diff:", max_bias_diff

        for i, l in enumerate(self.layers):
            l.momentum = momentums[i]
        print "Gradient is correct"
    """ END Gradient Checking """


    def __get_masked_input__(self, layer_input, input_masks, layer, ix):
        if type(layer) == DropOutLayer:
            if input_masks is None:
                mask = dropout_mask(layer_input, layer.drop_out_prob)
            else:
                mask = input_masks[ix]
            masked_input = np.multiply(mask, layer_input)
            return (mask, masked_input)
        else:
            return (None, layer_input)

    def __compute_gradient__(self, input_vectors, outputs, total_rows, layers, learning_rate, input_masks=None):

        rows = input_vectors.shape[0]
        inputs_T = input_vectors.T
        outputs_T = outputs.T

        layer_inputs =  []

        masks = []
        a = inputs_T
        outputs = []
        for ix, layer in enumerate(layers):
            layer_input = a
            mask, layer_input = self.__get_masked_input__(layer_input, input_masks, layer, ix)
            z, a = layer.prop_up(layer_input)

            masks.append(None)
            layer_inputs.append(layer_input)
            outputs.append(a)

        top_layer_output = a
        activations = layer_inputs[1:] + [top_layer_output]

        """ errors = mean( 0.5 sum squared error) (but gradient w.r.t. weights is sum(errors) """
        assert outputs_T.shape == top_layer_output.shape
        errors = (outputs_T - top_layer_output)

        # Compute weight updates
        delta = np.multiply( -(errors), layers[-1].derivative(activations[-1]))
        deltas = [delta]
        for i in range(len(layers) -1):
            ix = -(i + 1)
            upper_layer = layers[ix]
            layer = layers[ix-1]
            deriv = layer.derivative(activations[ix-1])
            """ THIS IS BACK PROP OF ERRORS TO HIDDEN LAYERS"""
            delta = np.multiply( np.dot(upper_layer.weights.T, delta), deriv)
            if masks[ix] is not None:
                delta = np.multiply(delta, masks[ix])
            deltas.insert(0, delta)

        #TODO Sparsity
        frows = float(rows)
        batch_proportion = frows / float(total_rows)

        gradients = []
        for i, layer in enumerate(layers):
            delta = deltas[i]
            layer_input_T = layer_inputs[i].T
            wtdelta = ((np.dot(delta, layer_input_T)) / (frows))

            """ For each weight, update it using the input activation * output delta. Compute a mean over all examples in the batch.

                The dot product is used here in a very clever  way to compute the activation * the delta
                for each input and hidden layer node and then dividing this by num rows to get the mean

                As the inputs are always 1, the activations are omitted for the bias
            """
            biasdelta = ((np.sum(delta, axis=1, keepdims=True) / (frows)))

            if layer.weight_decay > 0.0:
                """ Weight decay is typically not done for the bias as has marginal effect."""
                wtdelta += (layer.weight_decay * layer.weights)

            wds = learning_rate * batch_proportion * wtdelta
            bds = learning_rate * biasdelta
            gradients.append((wds, bds))

        """ return a list of errors (one item per row in mini batch) """
        return (errors.T, gradients)

    def __reset_layers__(self):
        for layer in self.layers:
            layer.revert_state()

    def __adjust_learning_rate__(self, previous_mae, mae):
        # error improved on the training data?
        if mae <= previous_mae:
            self.learning_rate *= self.lr_increase_multiplier
            for layer in self.layers:
                layer.save_state()
        else:
            #print "MAE increased from %s to %s. Decreasing learning rate from %s to %s" % \
            #      (str(previous_mae), str(mae),
            #       str(self.learning_rate), str(self.learning_rate * self.lr_decrease_multiplier))
            self.learning_rate *=  self.lr_decrease_multiplier
            self.__reset_layers__()
        # restrict learning rate to sensible bounds
        self.learning_rate = max(0.001, self.learning_rate)
        self.learning_rate = min(1.000, self.learning_rate)

    def __ensure_vector_format__(self, a):
        return get_array(a)

    def __validate_outputs__(self, outputs, layer):

        min_outp = np.min(outputs)
        max_outp = np.max(outputs)

        if layer.activation_fn == "sigmoid":
            self.__in_range__(min_outp, max_outp, 0.0, 1.0)
        elif layer.activation_fn == "softmax":
            unique = set(outputs.flatten())
            assert len(unique) == 2,                                "Wrong number of outputs. Outputs for softmax must be 0's and 1's"
            assert min(unique) == 0 and max(unique) ==1,            "Outputs for softmax must be 0's and 1's only"
            assert np.all(outputs.sum(axis=1) == 1.0), "Outputs for a softmax layer must sum to 1."

        elif layer.activation_fn == "tanh":
            self.__in_range__(min_outp, max_outp, -1.0, 1.0)
        elif layer.activation_fn == "relu":
            self.__in_range__(min_outp, max_outp, 0.0, np.inf)
        elif layer.activation_fn == "linear":
            pass
        else:
            raise Exception("Unknown activation function %s" % layer.activation_fn)

    def __in_range__(self, actual_min, actual_max, exp_min, exp_max):
        assert actual_max <= exp_max
        assert actual_min >= exp_min

if __name__ == "__main__":

    xs = [
        [1, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 0, 0, 0, 0, 0, 0],
        [0, 0, 1, 1, 0, 0, 0, 0],
        [1, 0, 0, 1, 0, 0, 0, 0],
        [1, 0, 0, 0, 1, 0, 1, 0],
        [0, 0, 0, 0, 0, 1, 0, 0],
        #[0, 1, 0, 0, 1, 0, 1, 0],
        #[1, 0, 1, 0, 1, 0, 0, 1]
    ]
    xs = np.array(xs)

    input_activation_fn  = "relu"

    # Having a linear output layer seems to work REALLY well
    output_activation_fn = "tanh"

    if input_activation_fn == "tanh":
        xs = (xs - 0.5) * 2.0

    ys = np.sum(xs, axis=1, keepdims=True) * 1.0
    ys = (ys - np.min(ys)) / (np.max(ys) - np.min(ys))
    ys = get_array(ys)
    """ Test as an Auto Encoder """
    soft_max_ys = []
    for x in xs:
        l = [0 for i in x]
        l[int(sum(x)) - 1] = 1
        soft_max_ys.append(l)
    soft_max_ys = get_array(soft_max_ys)

    ys = xs
    if output_activation_fn == "softmax":
        ys = soft_max_ys

    if output_activation_fn == "tanh" and np.min(ys.flatten()) == 0.0:
        ys = (ys - 0.5) * 2.0

    #num_hidden = int(round(np.log2(xs.shape[1]))) + 1
    num_hidden = int(round((xs.shape[1])) * 1.1)

    layers = [
        Layer(xs.shape[1], num_hidden,  activation_fn = input_activation_fn,  momentum=0.5),
        Layer(num_hidden,  num_hidden,  activation_fn = input_activation_fn,  momentum=0.5),
        Layer(num_hidden,  ys.shape[1], activation_fn = output_activation_fn, momentum=0.5),
    ]


    """ Note that the range of inputs for tanh is 2* sigmoid, and so the MAE should be 2* """
    nn = MLP(layers,
             learning_rate=0.5, weight_decay=0.0, epochs=100, batch_size=3,
             lr_increase_multiplier=1.1, lr_decrease_multiplier=0.9)

    nn.fit(     xs, ys, epochs=10,)

    """ Verify Gradient Calculation """
    nn.verify_gradient(xs, ys)

    hidden_activations = nn.predict(xs, 0)
    predictions = nn.predict(xs)

    if np.min(ys) == -1 and np.max(ys) == 1:
        ys = ys / 2.0 + 0.5
        predictions = predictions / 2.0 + 0.5

    print "ys"
    print np.round(ys, 1) * 1.0
    print "predictions"
    #print np.round(ae.prop_up(xs, xs)[0] * 3.0) * 0.3
    print np.round(predictions, 1)
    print predictions

    """
    print "Weights"
    print nn.layers[0].weights
    print ""
    print nn.layers[1].weights
    pass
    """

    """ TODO
    can we use a clustering algorithm to initialize the weights for hidden layer neurons? Normalize the data.
        learn k clusters. Implement a 3 layer NN with k hidden neurons, whose weights are initialized to the values for
        the cluster centroid (as that maximizes cosine similarity). Adjust weights for a non linearity such that centroid
        input values would cause it to fire (which means just scaling up the weight vector, probably 6x for sigmoid). Train
        network as normal (top layer has random initial weights). cf regular initialization of nnet.
    use LBFGS or conjugate gradient descent to optimize the parameters instead as supposedly faster

    >>>> DONE allow different activation functions per layer. Normally hidden layer uses RELU and dropout (http://fastml.com/deep-learning-these-days/)
          don't use RELU for output layer as you cannot correct for errors (i.e. gradient is 0 for negative updates!)
    >>>> DONE  Implement adaptive learning rate adjustments (see link above)
    >>>> DONE  Use finite gradients method to verify gradient descent calc. Bake into code as a flag ***
    >>>> DONE  Implement momentum (refer to early parts of this https://www.cs.toronto.edu/~hinton/csc2515/notes/lec6tutorial.pdf)
    >>>> ~DONE implement DROPOUT
    """